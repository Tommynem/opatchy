from __future__ import annotations

import os
import socket
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from email.message import Message
from pathlib import Path
from typing import IO, Protocol, TypeAlias, override

from .runner_process import run_spec
from .runner_registry import COMMAND_SPECS, ENDPOINT_SPECS
from .runner_types import (
    ArgumentPolicy,
    CommandExited,
    CommandMissing,
    CommandName,
    CommandOutputExceeded,
    CommandRejected,
    CommandResult,
    CommandSpec,
    CommandSucceeded,
    CommandTimedOut,
    EndpointCache,
    EndpointDownloaded,
    EndpointFailed,
    EndpointName,
    EndpointNotModified,
    EndpointOversized,
    EndpointRejected,
    EndpointResult,
    EndpointSpec,
    EndpointTimedOut,
    EndpointTlsFailed,
    redact_diagnostic,
)

HttpsRequest: TypeAlias = urllib.request.Request


class HttpsHeaders(Protocol):
    def get(self, name: str, failobj: str | None = None) -> str | None: ...


class HttpsResponse(Protocol):
    status: int
    headers: HttpsHeaders

    def read(self, amount: int = -1) -> bytes: ...

    def close(self) -> None: ...


__all__ = [
    "COMMAND_SPECS",
    "ArgumentPolicy",
    "ENDPOINT_SPECS",
    "CommandExited",
    "CommandMissing",
    "CommandName",
    "CommandOutputExceeded",
    "CommandRejected",
    "CommandResult",
    "CommandSpec",
    "CommandSucceeded",
    "CommandTimedOut",
    "EndpointCache",
    "EndpointDownloaded",
    "EndpointFailed",
    "EndpointName",
    "EndpointNotModified",
    "EndpointOversized",
    "EndpointRejected",
    "EndpointResult",
    "EndpointSpec",
    "EndpointTimedOut",
    "EndpointTlsFailed",
    "HttpsRequest",
    "HttpsResponse",
    "fetch_endpoint",
    "run_command",
]


def run_command(name: CommandName, arguments: tuple[str, ...] = ()) -> CommandResult:
    return run_spec(COMMAND_SPECS[name], arguments)


def fetch_endpoint(name: EndpointName, cache: EndpointCache) -> EndpointResult:
    spec = ENDPOINT_SPECS[name]
    headers = _conditional_headers(cache)
    url = spec.url
    for _ in range(spec.redirect_limit + 1):
        if not _valid_url(url, spec):
            return EndpointRejected(redact_diagnostic(url))
        request = urllib.request.Request(url, headers=headers, method="GET")  # noqa: S310 - _valid_url accepts only named HTTPS policy
        try:
            response = _open_https(
                request, spec.timeout_seconds, ssl.create_default_context()
            )
        except urllib.error.HTTPError as error:
            try:
                if error.code == 304:
                    return EndpointNotModified()
                location = error.headers.get("Location")
                if 300 <= error.code < 400 and location is not None:
                    url = urllib.parse.urljoin(url, location)
                    continue
                return EndpointFailed(f"HTTPS status {error.code}")
            finally:
                error.close()
        except urllib.error.URLError as error:
            return _network_failure(error)
        except TimeoutError as error:
            return EndpointTimedOut(redact_diagnostic(str(error)))
        try:
            status = response.status
            location = response.headers.get("Location")
            if 300 <= status < 400 and location is not None:
                url = urllib.parse.urljoin(url, location)
                continue
            if status == 304:
                return EndpointNotModified()
            if status != 200:
                return EndpointFailed(f"unexpected HTTPS status {status}")
            body = _read_body(response, spec.body_limit)
            if body is None:
                return EndpointOversized(
                    "HTTPS response body exceeds the endpoint limit"
                )
            etag = response.headers.get("ETag")
            last_modified = response.headers.get("Last-Modified")
        finally:
            response.close()
        try:
            _replace_cache(cache, body, etag, last_modified)
        except OSError as error:
            return EndpointFailed(redact_diagnostic(str(error)))
        return EndpointDownloaded(body, etag, last_modified)
    return EndpointRejected("HTTPS redirect limit exceeded")


def _open_https(
    request: HttpsRequest, timeout: float, context: ssl.SSLContext
) -> HttpsResponse:
    opener = urllib.request.build_opener(
        _NoRedirect(), urllib.request.HTTPSHandler(context=context)
    )
    return _open_with_opener(opener, request, timeout)


class _HttpsOpener(Protocol):
    def open(
        self,
        fullurl: str | HttpsRequest,
        data: bytes | None = None,
        timeout: float | None = None,
    ) -> HttpsResponse: ...


def _open_with_opener(
    opener: _HttpsOpener, request: HttpsRequest, timeout: float
) -> HttpsResponse:
    return opener.open(request, timeout=timeout)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    @override
    def redirect_request(
        self,
        req: HttpsRequest,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> None:
        return None


def _valid_url(url: str, spec: EndpointSpec) -> bool:
    parts = urllib.parse.urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and parts.hostname in spec.allowed_hosts
        and parts.username is None
        and parts.password is None
        and port in (None, 443)
        and parts.path in spec.allowed_paths
    )


def _network_failure(error: urllib.error.URLError) -> EndpointResult:
    reason = error.reason
    if isinstance(reason, ssl.SSLCertVerificationError):
        return EndpointTlsFailed(redact_diagnostic(str(reason)))
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return EndpointTimedOut(redact_diagnostic(str(reason)))
    return EndpointFailed(redact_diagnostic(str(reason)))


def _read_body(response: HttpsResponse, limit: int) -> bytes | None:
    chunks: list[bytes] = []
    remaining = limit
    while True:
        chunk = response.read(min(65536, remaining + 1))
        if not chunk:
            return b"".join(chunks)
        if len(chunk) > remaining:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)


def _conditional_headers(cache: EndpointCache) -> dict[str, str]:
    try:
        etag, last_modified = cache.metadata_path.read_text(
            encoding="utf-8"
        ).splitlines()[:2]
    except FileNotFoundError, OSError, UnicodeError, ValueError:
        return {"User-Agent": "Opatchy/1"}
    return {
        "User-Agent": "Opatchy/1",
        "If-None-Match": etag,
        "If-Modified-Since": last_modified,
    }


def _replace_cache(
    cache: EndpointCache, body: bytes, etag: str | None, last_modified: str | None
) -> None:
    cache.body_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(cache.body_path, body)
    _atomic_write(
        cache.metadata_path, f"{etag or ''}\n{last_modified or ''}\n".encode()
    )


def _atomic_write(path: Path, body: bytes) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            _ = temporary.write(body)
            temporary.flush()
            os.fsync(temporary.fileno())
        _ = os.replace(temporary_path, path)
    except OSError:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
