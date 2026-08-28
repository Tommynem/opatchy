.pragma library

var PRESENTATION_LAUNCHER = "/usr/bin/omarchy-launch-floating-terminal-with-presentation"
var OMARCHY_UPDATE = "/usr/bin/omarchy-update"
var FLATPAK = "/usr/bin/flatpak"

var OMARCHY_ARGV = [PRESENTATION_LAUNCHER, OMARCHY_UPDATE]
var FLATPAK_USER_ARGV = [PRESENTATION_LAUNCHER, FLATPAK, "--user", "update"]
var FLATPAK_SYSTEM_ARGV = [PRESENTATION_LAUNCHER, FLATPAK, "--system", "update"]
var UPDATE_ALL_ACTIONS = ["omarchy", "flatpak-user", "flatpak-system"]

function actionFor(name) {
  switch (name) {
  case "omarchy":
    return { name: name, argv: OMARCHY_ARGV.slice(), capabilities: ["launcher", "omarchyUpdate"] }
  case "flatpak-user":
    return { name: name, argv: FLATPAK_USER_ARGV.slice(), capabilities: ["launcher", "flatpak"] }
  case "flatpak-system":
    return { name: name, argv: FLATPAK_SYSTEM_ARGV.slice(), capabilities: ["launcher", "flatpak"] }
  default:
    return null
  }
}

function isEligible(snapshot, name, capabilities) {
  var action = actionFor(name)
  if (action === null || !hasCapabilities(action, capabilities) || !validSnapshot(snapshot)) return false

  switch (name) {
  case "omarchy":
    return hasCurrentUpdate(snapshot.payload, ["omarchy", "arch", "aur", "mise"])
  case "flatpak-user":
    return hasCurrentFlatpakUpdate(snapshot.payload, "user")
  case "flatpak-system":
    return hasCurrentFlatpakUpdate(snapshot.payload, "system")
  default:
    return false
  }
}

function eligibleUpdateActions(snapshot, capabilities) {
  return UPDATE_ALL_ACTIONS.filter(function(name) { return isEligible(snapshot, name, capabilities) })
}

function hasCapabilities(action, capabilities) {
  if (!isObject(capabilities)) return false
  return action.capabilities.every(function(capability) { return capabilities[capability] === true })
}

function validSnapshot(snapshot) {
  return isObject(snapshot) && isObject(snapshot.payload) && Array.isArray(snapshot.payload.sources)
    && Array.isArray(snapshot.payload.items)
}

function hasCurrentUpdate(payload, sourceNames) {
  return payload.items.some(function(item) {
    return isUpdate(item) && sourceNames.indexOf(item.source) !== -1 && currentSource(payload.sources, item.source)
  })
}

function hasCurrentFlatpakUpdate(payload, scope) {
  return payload.items.some(function(item) {
    return isUpdate(item) && item.source === "flatpak" && item.id.indexOf("flatpak:" + scope + ":") === 0
      && currentSource(payload.sources, "flatpak") && currentScope(payload.sources, scope)
  })
}

function isUpdate(item) {
  return isObject(item) && typeof item.id === "string" && typeof item.source === "string"
    && typeof item.candidate === "string" && item.candidate.length > 0
}

function currentSource(sources, name) {
  return sources.some(function(source) {
    return isCurrent(source) && source.source === name
  })
}

function currentScope(sources, scope) {
  var flatpak = sources.filter(function(source) { return isObject(source) && source.source === "flatpak" })[0]
  return isObject(flatpak) && Array.isArray(flatpak.scopes) && flatpak.scopes.some(function(value) {
    return isCurrent(value) && value.scope === scope
  })
}

function isCurrent(value) {
  return isObject(value) && value.status === "ok" && value.provenance === "live"
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}
