.pragma library

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

function nonnegativeInteger(value) {
  return typeof value === "number" && isFinite(value) && Math.floor(value) === value && value >= 0
}

function validInventoryRequest(value) {
  return isObject(value)
    && ["arch", "aur", "flatpak", "mise"].indexOf(value.source) !== -1
    && typeof value.query === "string"
    && value.query.length <= 128
    && nonnegativeInteger(value.offset)
    && value.offset <= 100000
    && nonnegativeInteger(value.limit)
    && value.limit >= 1
    && value.limit <= 100
}

function validStarRequest(value) {
  return isObject(value)
    && typeof value.itemId === "string"
    && value.itemId.length > 0
    && value.itemId.length <= 128
    && ["off", "temporary", "permanent"].indexOf(value.mode) !== -1
    && validSecurityWatchRequest(value)
}

function operationIdentity(value) {
  var identity = { id: value.id, kind: value.kind, itemId: value.itemId, mode: value.mode }
  if (hasSecurityWatchRequest(value)) {
    identity.securityAdvisory = value.securityAdvisory
    identity.fixedVersion = value.fixedVersion
    identity.cveIds = value.cveIds.slice()
  }
  return identity
}

function hasSecurityWatchRequest(value) {
  return value.securityAdvisory !== undefined
}

function validSecurityWatchRequest(value) {
  var fields = ["securityAdvisory", "fixedVersion", "cveIds"]
  var present = fields.filter(function(field) { return value[field] !== undefined }).length
  if (present === 0) return true
  if (
    present !== fields.length
    || value.mode !== "temporary"
    || !/^arch:[A-Za-z0-9@_+][A-Za-z0-9@._+-]{0,127}$/.test(value.itemId)
  ) return false
  if (
    typeof value.securityAdvisory !== "string"
    || !/^AVG-[0-9]{1,120}$/.test(value.securityAdvisory)
    || typeof value.fixedVersion !== "string"
    || !/^[\x20-\x7e]{1,256}$/.test(value.fixedVersion)
    || !Array.isArray(value.cveIds)
    || value.cveIds.length === 0
    || value.cveIds.length > 16
  ) return false
  for (var index = 0; index < value.cveIds.length; index += 1) {
    var cveId = value.cveIds[index]
    if (
      typeof cveId !== "string"
      || !/^CVE-[0-9]{4}-[0-9]{4,19}$/.test(cveId)
      || value.cveIds.indexOf(cveId) !== index
    ) return false
  }
  return true
}
