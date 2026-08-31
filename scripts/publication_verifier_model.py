from __future__ import annotations

from dataclasses import dataclass
from typing import Final, override

from helper.opatchy_helper.json_value import JsonValue, decode_json
from helper.opatchy_helper.models import ProtocolError

APPROVED_PLUGIN_ID: Final = "io.github.tommynem.opatchy"
APPROVED_REPOSITORY: Final = "Tommynem/opatchy"
MARKETPLACE_REPOSITORY: Final = "omacom/omarchy-plugin-marketplace"


@dataclass(slots=True)
class VerifierError(Exception):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class MarketplaceRegistry:
    active_plugin_ids: frozenset[str]
    retired_plugin_ids: frozenset[str]


def parse_object(document: str, description: str) -> dict[str, JsonValue]:
    try:
        value = decode_json(document)
    except ProtocolError as error:
        raise VerifierError(f"{description} is invalid JSON") from error
    match value:
        case dict() as object_value:
            return object_value
        case _:
            raise VerifierError(f"{description} must be a JSON object")


def parse_array(document: str, description: str) -> list[JsonValue]:
    try:
        value = decode_json(document)
    except ProtocolError as error:
        raise VerifierError(f"{description} is invalid JSON") from error
    match value:
        case list() as array_value:
            return array_value
        case _:
            raise VerifierError(f"{description} must be a JSON array")


def parse_target(document: str) -> None:
    match parse_object(document, "target repository"):
        case {
            "nameWithOwner": str(name),
            "isEmpty": bool(is_empty),
            "viewerPermission": "ADMIN",
        } if name == APPROVED_REPOSITORY and is_empty:
            return
        case _:
            raise VerifierError(
                "target repository is unavailable, unauthorized, or nonempty"
            )


def parse_published_repository(document: str) -> str:
    match parse_object(document, "published repository"):
        case {
            "nameWithOwner": str(name),
            "visibility": "PUBLIC",
            "url": "https://github.com/Tommynem/opatchy",
            "hasIssuesEnabled": True,
            "defaultBranchRef": {"name": str(branch)},
        } if name == APPROVED_REPOSITORY and branch:
            return branch
        case _:
            raise VerifierError(
                "published repository does not match approved invariants"
            )


def parse_default_branch(document: str, description: str) -> str:
    match parse_object(document, description):
        case {"defaultBranchRef": {"name": str(branch)}} if branch:
            return branch
        case {"default_branch": str(branch)} if branch:
            return branch
        case _:
            raise VerifierError(f"{description} has no usable default branch")


def parse_marketplace_registry(document: str) -> MarketplaceRegistry:
    match parse_object(document, "marketplace registry"):
        case {"sources": list(sources), "retiredPluginIds": list(retired)}:
            active = parse_active_plugin_ids(sources)
            retired_ids = parse_retired_plugin_ids(retired)
            return MarketplaceRegistry(active, retired_ids)
        case _:
            raise VerifierError("marketplace registry has an incomplete schema")


def parse_active_plugin_ids(sources: list[JsonValue]) -> frozenset[str]:
    active: set[str] = set()
    for source in sources:
        match source:
            case {"plugins": dict(plugins)}:
                for plugin_id in plugins:
                    if not plugin_id or plugin_id in active:
                        raise VerifierError(
                            "marketplace registry has malformed plugin maps"
                        )
                    active.add(plugin_id)
            case {"plugins": _}:
                raise VerifierError("marketplace registry has malformed plugin maps")
            case dict():
                continue
            case _:
                raise VerifierError("marketplace registry has malformed plugin maps")
    return frozenset(active)


def parse_retired_plugin_ids(retired: list[JsonValue]) -> frozenset[str]:
    ids: set[str] = set()
    for entry in retired:
        match entry:
            case str(plugin_id) if plugin_id and plugin_id not in ids:
                ids.add(plugin_id)
            case _:
                raise VerifierError(
                    "marketplace registry has malformed retiredPluginIds"
                )
    return frozenset(ids)


def require_sha(value: str, description: str) -> str:
    sha = value.strip()
    if len(sha) != 40 or any(character not in "0123456789abcdef" for character in sha):
        raise VerifierError(f"{description} must be a lowercase full commit SHA")
    return sha


def require_successful_ci(document: str, sha: str) -> None:
    runs = parse_array(document, "Validate workflow response")
    matched = 0
    for run in runs:
        match run:
            case {
                "headSha": str(head_sha),
                "status": str(status),
                "conclusion": str(conclusion),
            }:
                if head_sha == sha:
                    matched += 1
                    if status != "completed" or conclusion != "success":
                        raise VerifierError(
                            "expected SHA has no successful Validate workflow run"
                        )
            case _:
                raise VerifierError("Validate workflow response has an invalid run")
    if matched == 0:
        raise VerifierError("expected SHA has no successful Validate workflow run")
