from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Final

from .runner_types import EndpointCache

_MAX_METADATA_BYTES: Final = 2_048
_MAX_VALIDATOR_LENGTH: Final = 1_024
_DIGEST_LENGTH: Final = 64


@dataclass(frozen=True, slots=True)
class CacheValidators:
    etag: str
    last_modified: str


def read_cache_validators(cache: EndpointCache, body: bytes) -> CacheValidators | None:
    try:
        with cache.metadata_path.open("rb") as metadata_file:
            metadata = metadata_file.read(_MAX_METADATA_BYTES + 1)
    except OSError:
        return None
    return parse_cache_metadata(metadata, body)


def parse_cache_metadata(metadata: bytes, body: bytes) -> CacheValidators | None:
    if len(metadata) > _MAX_METADATA_BYTES:
        return None
    try:
        etag, last_modified, digest, ending = metadata.decode("ascii").split("\n")
    except UnicodeDecodeError, ValueError:
        return None
    if (
        ending
        or not _valid_digest(digest)
        or not hmac.compare_digest(digest, hashlib.sha256(body).hexdigest())
    ):
        return None
    if not _safe_validator(etag) or not _safe_validator(last_modified):
        return None
    if not etag and not last_modified:
        return None
    return CacheValidators(etag, last_modified)


def serialize_cache_metadata(
    body: bytes, etag: str | None, last_modified: str | None
) -> bytes:
    safe_etag = etag if etag is not None and _safe_validator(etag) else ""
    safe_last_modified = (
        last_modified
        if last_modified is not None and _safe_validator(last_modified)
        else ""
    )
    return f"{safe_etag}\n{safe_last_modified}\n{hashlib.sha256(body).hexdigest()}\n".encode()


def _safe_validator(value: str) -> bool:
    return len(value) <= _MAX_VALIDATOR_LENGTH and all(
        " " <= char <= "~" for char in value
    )


def _valid_digest(value: str) -> bool:
    return len(value) == _DIGEST_LENGTH and all(
        char in "0123456789abcdef" for char in value
    )
