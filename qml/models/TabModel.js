.pragma library

var TAB_NAMES = ["Security", "Omarchy", "System", "AUR", "Flatpak", "mise"]
var TAB_SOURCES = ["security", "omarchy", "arch", "aur", "flatpak", "mise"]

function healthForStatus(status) {
  switch (status) {
  case "ok": return health("OK", "Current", "Current source data")
  case "not_applicable": return health("N/A", "Not applicable", "Not applicable on this host")
  case "stale": return health("~", "Last known", "Last known source data; a current scan is unavailable")
  case "invalid": return health("!", "Incompatible", "Incompatible source data for this Opatchy version")
  case "missing_dependency":
  case "offline":
  case "timeout":
  case "error": return health("!", "Unavailable", "Unavailable current source data")
  default: return health("?", "Incompatible", "Incompatible source status for this Opatchy version")
  }
}

function buildPanelState(snapshot, runtime, currentTime) {
  var payload = snapshot && snapshot.payload ? snapshot.payload : null
  var tabs = TAB_NAMES.map(function(name, index) {
    return tab(name, TAB_SOURCES[index], payload)
  })
  var scanState = payload ? payload.scanState : "failed"
  var sourceBanner = tabs.some(function(value) { return value.health.text.toLowerCase().indexOf("last known") !== -1 })
    ? "Last known data is shown for unavailable sources."
    : ""
  var coverageBanner = tabs.some(function(value) { return value.health.text.indexOf("Partial coverage") === 0 })
    ? "Partial source coverage is shown in the affected tabs."
    : ""
  var scanBanner = scanState === "partial"
    ? "Partial scan: some source results are unavailable."
    : (scanState === "failed" ? "Scan failed: showing the last known result." : "")
  return {
    tabs: tabs,
    summaryText: summaryText(payload ? payload.summary : null),
    bannerText: joinText(scanBanner, joinText(sourceBanner, coverageBanner)),
    failureText: failureText(runtime ? runtime.lastFailureKind : ""),
    refreshText: runtime && runtime.refreshing ? "Refreshing" : "Refresh",
    lastAttemptText: ageText(runtime ? runtime.lastAttemptAt : null, currentTime),
    lastSuccessText: ageText(successAt(snapshot, runtime), currentTime),
  }
}

function hasUrgentSecurity(snapshot) {
  var groups = snapshot && snapshot.payload && Array.isArray(snapshot.payload.findings)
    ? snapshot.payload.findings
    : []
  return groups.some(function(group) {
    return Array.isArray(group.findings) && group.findings.some(function(finding) {
      return finding.severity === "high" || finding.severity === "critical"
    })
  })
}

function restoreSelection(value, urgentSecurity) {
  if (TAB_NAMES.indexOf(value) !== -1) return value
  if (urgentSecurity) return "Security"
  return TAB_NAMES[0]
}

function persistSelection(shell, moduleName, settings, tab) {
  if (!shell || typeof shell.updateEntryInline !== "function" || TAB_NAMES.indexOf(tab) === -1) return false
  var next = Object.assign({}, settings || {}, { "lastSelectedTab": tab })
  return shell.updateEntryInline(moduleName, next) === true
}

function nextTab(current, direction) {
  var index = TAB_NAMES.indexOf(current)
  if (index < 0) index = 0
  var step = direction < 0 ? -1 : 1
  return TAB_NAMES[(index + step + TAB_NAMES.length) % TAB_NAMES.length]
}

function tab(name, source, payload) {
  var sourceState = sourceFor(payload, source)
  var count = name === "Security"
    ? number(payload && payload.summary ? payload.summary.securityFindings : 0)
    : itemCount(payload && payload.items, source)
  var health = name === "Security"
    ? securityHealth(sourceState, sourceFor(payload, "cisa-kev"))
    : healthForStatus(sourceState ? sourceState.status : "unknown")
  return { name: name, source: source, count: count, glyph: health.glyph, healthText: health.text, tooltip: health.tooltip, health: health }
}

function securityHealth(security, kev) {
  var securityHealth = healthForStatus(security ? security.status : "unknown")
  if (!security || security.status !== "ok") return securityHealth
  if (kev && kev.status === "ok") return securityHealth
  if (kev && kev.status === "stale") {
    return health("~", "Partial coverage, last known", "Arch security data is current. CISA KEV coverage is last known.")
  }
  if (kev && kev.status === "not_applicable") {
    return health("N/A", "Partial coverage, not applicable", "Arch security data is current. CISA KEV coverage is not applicable.")
  }
  return health("!", "Partial coverage", "Arch security data is current. CISA KEV coverage is unavailable.")
}

function sourceFor(payload, name) {
  if (!payload || !Array.isArray(payload.sources)) return null
  return payload.sources.filter(function(value) { return value.source === name })[0] || null
}

function itemCount(items, source) {
  if (!Array.isArray(items)) return 0
  return items.filter(function(item) { return item.source === source }).length
}

function summaryText(summary) {
  var total = number(summary ? summary.totalUpdates : 0)
  var findings = number(summary ? summary.securityFindings : 0)
  var degraded = number(summary ? summary.degradedSources : 0)
  return total + " updates, " + findings + " security findings, " + degraded + " sources need attention"
}

function failureText(kind) {
  switch (kind) {
  case "incompatible": return "Incompatible data. Showing the last known result; refresh after updating Opatchy."
  case "timeout": return "Refresh timed out. Showing the last known result."
  case "output": return "Refresh output was too large. Showing the last known result."
  case "command": return "Refresh command failed. Showing the last known result."
  case "helper": return "Opatchy could not read the helper result. Showing the last known result."
  case "transport": return "Refresh transport is unavailable. Showing the last known result."
  default: return ""
  }
}

function ageText(value, currentTime) {
  if (typeof value !== "number" || !isFinite(value)) return "not recorded"
  var seconds = Math.max(0, Math.floor((number(currentTime) - value) / 1000))
  if (seconds < 60) return plural(seconds, "second") + " ago"
  var minutes = Math.floor(seconds / 60)
  if (minutes < 60) return plural(minutes, "minute") + " ago"
  var hours = Math.floor(minutes / 60)
  if (hours < 24) return plural(hours, "hour") + " ago"
  return plural(Math.floor(hours / 24), "day") + " ago"
}

function successAt(snapshot) {
  return snapshot && typeof snapshot.generatedAt === "string" ? Date.parse(snapshot.generatedAt) : null
}

function health(glyph, text, tooltip) { return { glyph: glyph, text: text, tooltip: tooltip } }
function joinText(first, second) { return first && second ? first + " " + second : first || second }
function number(value) { return typeof value === "number" && isFinite(value) && value >= 0 ? value : 0 }
function plural(value, unit) { return value + " " + unit + (value === 1 ? "" : "s") }
