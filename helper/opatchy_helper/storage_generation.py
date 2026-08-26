import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Final, NoReturn

from .json_value import JsonObject, JsonValue, decode_json
from .models import (
    ErrorCode,
    ErrorInfo,
    InventoryResponse,
    ProtocolError,
    SnapshotResponse,
    SourceName,
)
from .protocol import decode_response, encode_response
from .storage_state import decode_state, encode_state
from .storage_types import PersistentState

GENERATION_SCHEMA_VERSION: Final = 1
_FIELDS: Final = frozenset(
    (
        "schemaVersion",
        "order",
        "snapshot",
        "inventories",
        "state",
        "lastGood",
        "lastGoodKeys",
    )
)
_LAST_GOOD_KEYS: Final = frozenset(
    (*tuple(source.value for source in SourceName), "flatpak:user", "flatpak:system")
)


@dataclass(frozen=True, slots=True)
class GenerationBundle:
    order: int
    snapshot: SnapshotResponse
    inventories: tuple[InventoryResponse, ...]
    state: PersistentState
    last_good: SnapshotResponse
    last_good_keys: tuple[str, ...]


def encode_generation(bundle: GenerationBundle, now: datetime) -> bytes:
    """Encode only independently validated protocol and state cache objects."""
    _validate_bundle(bundle)
    value: JsonObject = {
        "schemaVersion": GENERATION_SCHEMA_VERSION,
        "order": bundle.order,
        "snapshot": _encoded_response(bundle.snapshot),
        "inventories": [_encoded_response(response) for response in bundle.inventories],
        "state": _encoded_state(bundle.state, now),
        "lastGood": _encoded_response(bundle.last_good),
        "lastGoodKeys": list(bundle.last_good_keys),
    }
    return (
        json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        + b"\n"
    )


def decode_generation(raw: bytes) -> GenerationBundle:
    """Decode a generation only when every nested cache object validates."""
    try:
        value = decode_json(raw.decode("utf-8"))
    except UnicodeDecodeError as error:
        _fail("generation cache is not UTF-8", error)
    document = _document(value)
    if frozenset(document) != _FIELDS:
        _fail("generation cache fields are invalid")
    schema_version = _integer(document["schemaVersion"])
    if schema_version != GENERATION_SCHEMA_VERSION:
        _fail("generation cache schema is unsupported")
    snapshot = _snapshot(document["snapshot"])
    inventories = _inventories(document["inventories"])
    state = decode_state(_decoded_bytes(document["state"]))
    last_good = _snapshot(document["lastGood"])
    keys = _keys(document["lastGoodKeys"])
    bundle = GenerationBundle(
        _integer(document["order"]), snapshot, inventories, state, last_good, keys
    )
    _validate_bundle(bundle)
    return bundle


def _validate_bundle(bundle: GenerationBundle) -> None:
    if type(bundle.order) is not int or bundle.order < 0:
        _fail("generation order is invalid")
    _ = encode_response(bundle.snapshot)
    _ = encode_response(bundle.last_good)
    sources = tuple(response.payload.source for response in bundle.inventories)
    if len(sources) != len(set(sources)) or sources != tuple(sorted(sources)):
        _fail("generation inventories are not deterministically unique")
    for inventory in bundle.inventories:
        _ = encode_response(inventory)
    _ = encode_state(bundle.state, bundle.snapshot.generated_at)
    if len(bundle.last_good_keys) != len(set(bundle.last_good_keys)):
        _fail("generation last-good keys are duplicated")
    if any(key not in _LAST_GOOD_KEYS for key in bundle.last_good_keys):
        _fail("generation last-good key is invalid")


def _encoded_response(response: SnapshotResponse | InventoryResponse) -> str:
    return base64.b64encode(encode_response(response)).decode("ascii")


def _encoded_state(state: PersistentState, now: datetime) -> str:
    return base64.b64encode(encode_state(state, now)).decode("ascii")


def _document(value: JsonValue) -> JsonObject:
    if type(value) is dict:
        return value
    _fail("generation cache must be an object")


def _integer(value: JsonValue) -> int:
    if type(value) is int and value >= 0:
        return value
    _fail("generation integer is invalid")


def _snapshot(value: JsonValue) -> SnapshotResponse:
    response = decode_response(_decoded_bytes(value))
    match response:
        case SnapshotResponse():
            return response
        case _:
            _fail("generation snapshot has an invalid response kind")


def _inventories(value: JsonValue) -> tuple[InventoryResponse, ...]:
    if type(value) is not list:
        _fail("generation inventories must be an array")
    inventories: list[InventoryResponse] = []
    for entry in value:
        response = decode_response(_decoded_bytes(entry))
        match response:
            case InventoryResponse():
                inventories.append(response)
            case _:
                _fail("generation inventory has an invalid response kind")
    return tuple(inventories)


def _keys(value: JsonValue) -> tuple[str, ...]:
    if type(value) is not list or any(type(entry) is not str for entry in value):
        _fail("generation last-good keys are invalid")
    return tuple(entry for entry in value if type(entry) is str)


def _decoded_bytes(value: JsonValue) -> bytes:
    if type(value) is not str:
        _fail("generation encoded value is invalid")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as error:
        _fail("generation encoded value is invalid", error)


def _fail(message: str, error: Exception | None = None) -> NoReturn:
    raised = ProtocolError(ErrorInfo(ErrorCode.INVALID_ENVELOPE, message))
    if error is None:
        raise raised
    raise raised from error
