"""Strict CISA KEV schema parser retaining only validated CVE identifiers."""

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final

from ..json_value import JsonValue, decode_json
from ..models import ProtocolError, Provenance

_CVE: Final = re.compile(r"CVE-[0-9]{4}-[0-9]{4,19}")
_CWE: Final = re.compile(r"CWE-[0-9]+")
_MAX_RECORDS: Final = 20_000
_MAX_STRING: Final = 2_048
_REQUIRED = frozenset(
    {
        "cveID",
        "vendorProject",
        "product",
        "vulnerabilityName",
        "dateAdded",
        "shortDescription",
        "requiredAction",
        "dueDate",
    }
)
_OPTIONAL_STRINGS = frozenset({"knownRansomwareCampaignUse", "notes"})


@dataclass(frozen=True, slots=True)
class KevCatalog:
    cve_ids: frozenset[str]
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class KevFeedInvalid:
    diagnostic: str


@dataclass(frozen=True, slots=True)
class KevUnavailable:
    diagnostic: str


def parse_kev(
    raw: bytes, provenance: Provenance = Provenance.LIVE
) -> KevCatalog | KevFeedInvalid:
    """Parse a complete KEV catalog, rejecting count mismatches and invalid CVEs."""
    try:
        decoded = decode_json(raw.decode("utf-8"))
    except UnicodeDecodeError:
        return KevFeedInvalid("KEV feed is not UTF-8")
    except ProtocolError:
        return KevFeedInvalid("KEV feed is not valid JSON")
    if type(decoded) is not dict:
        return KevFeedInvalid("KEV root is not an object")
    required = {"catalogVersion", "dateReleased", "count", "vulnerabilities"}
    if not required.issubset(decoded):
        return KevFeedInvalid("KEV root omits a required field")
    if not _string(decoded["catalogVersion"]) or not _datetime(decoded["dateReleased"]):
        return KevFeedInvalid("KEV metadata has an invalid type")
    count = decoded["count"]
    vulnerabilities = decoded["vulnerabilities"]
    if type(count) is not int or type(vulnerabilities) is not list:
        return KevFeedInvalid("KEV count or vulnerabilities has an invalid type")
    if count != len(vulnerabilities) or count > _MAX_RECORDS:
        return KevFeedInvalid("KEV count is invalid")
    cve_ids: set[str] = set()
    for record in vulnerabilities:
        cve_id = _record_cve(record)
        if cve_id is None or cve_id in cve_ids:
            return KevFeedInvalid("KEV vulnerability has an invalid schema")
        cve_ids.add(cve_id)
    return KevCatalog(frozenset(cve_ids), provenance)


def _record_cve(value: JsonValue) -> str | None:
    if type(value) is not dict or not _REQUIRED.issubset(value):
        return None
    for field in _REQUIRED - frozenset({"dateAdded", "dueDate"}):
        if not _string(value[field]):
            return None
    if not _date(value["dateAdded"]) or not _date(value["dueDate"]):
        return None
    for field in _OPTIONAL_STRINGS:
        if field in value and not _string(value[field]):
            return None
    if "cwes" in value and _cwes(value["cwes"]) is None:
        return None
    cve_id = value["cveID"]
    if type(cve_id) is not str or _CVE.fullmatch(cve_id) is None:
        return None
    return cve_id


def _string(value: JsonValue) -> str | None:
    if (
        type(value) is str
        and 0 < len(value) <= _MAX_STRING
        and value.isprintable()
        and "://" not in value
    ):
        return value
    return None


def _cwes(value: JsonValue) -> tuple[str, ...] | None:
    if type(value) is not list or len(value) > _MAX_RECORDS:
        return None
    values = tuple(_string(entry) for entry in value)
    if any(entry is None or _CWE.fullmatch(entry) is None for entry in values):
        return None
    cwes = tuple(entry for entry in values if entry is not None)
    return cwes if len(set(cwes)) == len(cwes) else None


def _date(value: JsonValue) -> str | None:
    string = _string(value)
    if string is None or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", string) is None:
        return None
    try:
        _ = date.fromisoformat(string)
    except ValueError:
        return None
    return string


def _datetime(value: JsonValue) -> str | None:
    string = _string(value)
    if string is None or "T" not in string:
        return None
    try:
        _ = datetime.fromisoformat(string.replace("Z", "+00:00"))
    except ValueError:
        return None
    return string
