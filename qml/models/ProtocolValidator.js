.pragma library

.import "StrictJson.js" as StrictJson

var RESPONSE_KINDS = ["snapshot", "inventory", "star-result", "error"]
var SCAN_STATES = ["complete", "partial", "failed"]
var SOURCE_NAMES = ["security", "cisa-kev", "omarchy", "arch", "aur", "flatpak", "mise"]
var SOURCE_SCOPES = ["user", "system"]
var ITEM_SOURCES = ["omarchy", "arch", "aur", "flatpak", "mise"]
var INVENTORY_SOURCES = ["arch", "aur", "flatpak", "mise"]
var SOURCE_STATUSES = ["ok", "not_applicable", "missing_dependency", "offline", "timeout", "error", "invalid", "stale"]
var PROVENANCES = ["live", "cache", "last_good", "fallback"]
var WATCH_MODES = ["off", "temporary", "permanent"]
var SEVERITIES = ["unknown", "low", "medium", "high", "critical"]
var ARCH_STATUSES = ["Unknown", "Vulnerable", "Testing", "Fixed", "Not affected"]
var KEV_STATUSES = ["listed", "not_listed", "unavailable"]
var NOTIFICATION_STATUSES = ["delivered", "pending", "suppressed", "failed"]
var ERROR_CODES = ["CLI_USAGE", "STATE_UNAVAILABLE", "INVALID_UTF8", "PAYLOAD_TOO_LARGE", "MALFORMED_JSON", "INVALID_TYPE", "MISSING_FIELD", "UNKNOWN_FIELD", "PROTOCOL_VERSION_MISSING", "PROTOCOL_VERSION_INVALID", "PROTOCOL_VERSION_FUTURE", "UNKNOWN_ENUM", "INVALID_TIMESTAMP", "INVALID_ENVELOPE", "DUPLICATE_ITEM_ID", "DUPLICATE_FINDING_ID", "OUTPUT_TOO_LARGE", "SOURCE_INVALID", "SOURCE_UNAVAILABLE"]

function parseResponse(text) {
  if (typeof text !== "string") return failure("helper output is not text")
  if (StrictJson.hasDuplicateObjectKey(text)) return failure("helper output contains duplicate object keys")
  var value
  try { value = JSON.parse(text) } catch (error) { return failure("helper output is not valid JSON") }
  if (!object(value) || !envelope(value)) return failure("helper response envelope is invalid")
  if (value.protocolVersion !== 1) return failure("helper protocol version is unsupported")
  if (!member(RESPONSE_KINDS, value.kind)) return failure("helper response kind is unsupported")
  if (!timestamp(value.generatedAt) || !bounded(value.generationId)) return failure("helper response metadata is invalid")
  if (value.kind === "error") return validError(value.error) ? success(value) : failure("helper error response is invalid")
  if (value.kind === "snapshot") return validSnapshot(value.payload) ? success(value) : failure("helper snapshot is invalid")
  if (value.kind === "inventory") return validInventory(value.payload) ? success(value) : failure("helper inventory is invalid")
  return validStarResult(value.payload) ? success(value) : failure("helper star result is invalid")
}

function envelope(value) {
  return exactKeys(value, value.kind === "error"
    ? ["protocolVersion", "kind", "generatedAt", "generationId", "error"]
    : ["protocolVersion", "kind", "generatedAt", "generationId", "payload"])
}

function validSnapshot(value) {
  if (!exactKeys(value, ["scanState", "sources", "summary", "items", "findings", "notifications"])) return false
  return member(SCAN_STATES, value.scanState) && Array.isArray(value.sources) && Array.isArray(value.items)
    && Array.isArray(value.findings) && Array.isArray(value.notifications) && validSummary(value.summary)
    && validSources(value.sources) && validItems(value.items) && validGroups(value.findings, value.items)
    && validNotifications(value.notifications)
}

function validSources(values) {
  if (!unique(values, function(value) { return object(value) ? value.source : null }) || values.length !== SOURCE_NAMES.length) return false
  for (var index = 0; index < values.length; index += 1) if (!validSource(values[index])) return false
  return SOURCE_NAMES.every(function(name) { return values.some(function(value) { return value.source === name }) })
}

function validSource(value) {
  var required = ["source", "status", "provenance", "observedAt", "freshUntil", "cause"]
  if (!allowedObject(value, required.concat(["scopes"])) || !hasKeys(value, required)) return false
  if (!member(SOURCE_NAMES, value.source) || !member(SOURCE_STATUSES, value.status) || !member(PROVENANCES, value.provenance)) return false
  if (!timestamp(value.observedAt) || !timestamp(value.freshUntil) || !nullableError(value.cause)) return false
  if (!("scopes" in value)) return true
  if (!Array.isArray(value.scopes)) return false
  if (value.scopes.length === 0) return true
  return value.source === "flatpak" && validScopes(value.scopes)
}

function validScopes(values) {
  if (!unique(values, function(value) { return object(value) ? value.scope : null }) || values.length !== SOURCE_SCOPES.length) return false
  return values.every(validScope) && SOURCE_SCOPES.every(function(scope) { return values.some(function(value) { return value.scope === scope }) })
}

function validScope(value) {
  var keys = ["scope", "status", "provenance", "observedAt", "freshUntil", "cause"]
  return exactKeys(value, keys) && member(SOURCE_SCOPES, value.scope) && member(SOURCE_STATUSES, value.status)
    && member(PROVENANCES, value.provenance) && timestamp(value.observedAt) && timestamp(value.freshUntil) && nullableError(value.cause)
}

function validSummary(value) {
  var keys = ["totalUpdates", "watchedUpdates", "securityFindings", "degradedSources"]
  return exactKeys(value, keys) && keys.every(function(key) { return nonnegativeInteger(value[key]) })
}

function validItems(values) {
  return unique(values, function(value) { return object(value) ? value.id : null }) && values.every(validItem)
}

function validItem(value) {
  var required = ["id", "source", "label", "installed", "candidate", "watchMode", "watchable", "provenance"]
  if (!allowedObject(value, required.concat(["installedFingerprint", "candidateFingerprint"])) || !hasKeys(value, required)) return false
  return bounded(value.id) && member(ITEM_SOURCES, value.source) && bounded(value.label) && nullableString(value.installed)
    && nullableString(value.candidate) && member(WATCH_MODES, value.watchMode) && typeof value.watchable === "boolean"
    && member(PROVENANCES, value.provenance) && optionalBounded(value, "installedFingerprint") && optionalBounded(value, "candidateFingerprint")
}

function validGroups(values, items) {
  return unique(values, function(value) { return object(value) ? value.itemId : null }) && values.every(function(group) { return validGroup(group, items) })
}

function validGroup(value, items) {
  if (!exactKeys(value, ["itemId", "findings"]) || typeof value.itemId !== "string" || value.itemId.indexOf("arch:") !== 0 || !Array.isArray(value.findings) || value.findings.length === 0) return false
  var item = items.filter(function(candidate) { return candidate.id === value.itemId })[0]
  return (!item || item.source === "arch") && unique(value.findings, function(finding) { return object(finding) ? finding.id : null })
    && value.findings.every(function(finding) { return validFinding(finding, value.itemId) })
}

function validFinding(value, groupItemId) {
  var keys = ["id", "itemId", "advisoryId", "cveIds", "severity", "fixedVersion", "installedVersion", "knownExploited", "kevStatus", "kevProvenance", "provenance", "status", "type"]
  return exactKeys(value, keys) && average(value.id) && value.itemId === groupItemId && value.advisoryId === value.id
    && Array.isArray(value.cveIds) && value.cveIds.every(function(cve) { return typeof cve === "string" })
    && member(SEVERITIES, value.severity) && nullableString(value.fixedVersion) && nullableString(value.installedVersion)
    && typeof value.knownExploited === "boolean" && member(KEV_STATUSES, value.kevStatus) && nullableProvenance(value.kevProvenance)
    && member(PROVENANCES, value.provenance) && member(ARCH_STATUSES, value.status) && bounded(value.type) && validKev(value)
}

function validNotifications(values) {
  return unique(values, function(value) { return object(value) ? value.fingerprint : null }) && values.every(function(value) {
    return exactKeys(value, ["fingerprint", "status"]) && typeof value.fingerprint === "string" && member(NOTIFICATION_STATUSES, value.status)
  })
}

function validInventory(value) {
  return exactKeys(value, ["source", "total", "items"]) && member(INVENTORY_SOURCES, value.source) && nonnegativeInteger(value.total)
    && Array.isArray(value.items) && value.total >= value.items.length && validItems(value.items)
    && value.items.every(function(item) { return item.source === value.source })
}

function validStarResult(value) {
  return exactKeys(value, ["itemId", "mode"]) && bounded(value.itemId) && member(WATCH_MODES, value.mode)
}

function validError(value) {
  return exactKeys(value, ["code", "message"]) && member(ERROR_CODES, value.code) && bounded(value.message, 512)
}

function validKev(value) {
  if (value.kevStatus === "listed") return value.knownExploited && value.kevProvenance !== null
  if (value.kevStatus === "not_listed") return !value.knownExploited && value.kevProvenance !== null
  return !value.knownExploited && value.kevProvenance === null
}

function nullableError(value) { return value === null || validError(value) }
function nullableString(value) { return value === null || typeof value === "string" }
function nullableProvenance(value) { return value === null || member(PROVENANCES, value) }
function optionalBounded(value, key) { return !(key in value) || value[key] === null || bounded(value[key]) }
function average(value) { return bounded(value) && /^AVG-[0-9]+$/.test(value) }
function bounded(value, maximum) { return typeof value === "string" && value.length > 0 && value.length <= (maximum || 128) }
function timestamp(value) { return typeof value === "string" && value.length >= 21 && value.charAt(10) === "T" && value.charAt(value.length - 1) === "Z" && !isNaN(Date.parse(value)) }
function nonnegativeInteger(value) { return typeof value === "number" && isFinite(value) && Math.floor(value) === value && value >= 0 }
function member(values, value) { return values.indexOf(value) !== -1 }
function object(value) { return value !== null && typeof value === "object" && !Array.isArray(value) }
function exactKeys(value, keys) { return object(value) && Object.keys(value).length === keys.length && hasKeys(value, keys) }
function allowedObject(value, keys) { return object(value) && Object.keys(value).every(function(key) { return member(keys, key) }) }
function hasKeys(value, keys) { return keys.every(function(key) { return key in value }) }
function unique(values, identity) { var seen = []; for (var index = 0; index < values.length; index += 1) { var key = identity(values[index]); if (key === null || seen.indexOf(key) !== -1) return false; seen.push(key) } return true }
function success(value) { return { ok: true, value: value } }
function failure(error) { return { ok: false, error: error } }
