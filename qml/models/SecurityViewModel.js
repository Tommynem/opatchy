.pragma library

var MAX_PRESENTATION_LENGTH = 256
var SEVERITIES = ["critical", "high", "medium", "low", "unknown"]
var CURRENT_PROVENANCES = ["live", "fallback", "cache"]

function securityView(snapshot, currentTime) {
  var payload = snapshot && snapshot.payload && typeof snapshot.payload === "object" ? snapshot.payload : null
  var sources = payload && Array.isArray(payload.sources) ? payload.sources : []
  var security = sourceFor(sources, "security")
  var kev = sourceFor(sources, "cisa-kev")
  var archCoverage = coverage("Arch security data", security, currentTime)
  var kevCoverage = coverage("CISA KEV data", kev, currentTime)
  if (!isRetainedOrCurrent(security, currentTime)) return unknownView(archCoverage, kevCoverage)

  var groups = groupsFor(payload ? payload.findings : [], security, archCoverage, kevCoverage)
  if (!isCurrent(security, currentTime)) return lastKnownView(groups, archCoverage, kevCoverage)
  if (groups.length === 0) return cleanView(archCoverage, kevCoverage)
  return findingsView(groups, archCoverage, kevCoverage)
}

function cleanView(archCoverage, kevCoverage) {
  return state("clean", "No known matching advisories in the current Arch data", [], archCoverage, kevCoverage)
}

function findingsView(groups, archCoverage, kevCoverage) {
  return state("findings", "Current Arch security findings are shown below.", groups, archCoverage, kevCoverage)
}

function lastKnownView(groups, archCoverage, kevCoverage) {
  return state("last_known", "Arch security results are last known; current results are unavailable.", groups, archCoverage, kevCoverage)
}

function unknownView(archCoverage, kevCoverage) {
  return state("unknown", "Arch security results are unknown because current evidence is unavailable or incompatible.", [], archCoverage, kevCoverage)
}

function state(kind, statusText, groups, archCoverage, kevCoverage) {
  return { kind: kind, statusText: statusText, groups: groups, archCoverage: archCoverage, kevCoverage: kevCoverage }
}

function groupsFor(values, security, archCoverage, kevCoverage) {
  if (!Array.isArray(values)) return []
  var groups = values.filter(validGroup).map(function(group) {
    var rows = group.findings.filter(validFinding).map(function(finding) {
      return findingRow(finding, archCoverage, kevCoverage)
    }).sort(compareFindings)
    return { watchTarget: group.itemId, packageName: presentationText(group.itemId.slice(5)), findings: rows }
  }).filter(function(group) { return group.findings.length > 0 })
  return groups.sort(compareGroups)
}

function findingRow(finding, archCoverage, kevCoverage) {
  return {
    advisoryId: finding.id,
    cveIds: finding.cveIds.filter(canonicalCve),
    severity: finding.severity,
    versionText: versionText(finding),
    status: presentationText(finding.status),
    type: presentationText(finding.type),
    provenance: presentationText(finding.provenance),
    kevText: kevText(finding.kevStatus),
    kevProvenance: presentationText(finding.kevProvenance),
    ageText: archCoverage.ageText,
    sourceCoverageText: archCoverage.text + ". " + kevCoverage.text,
    knownExploited: finding.knownExploited === true,
    hasFixedVersion: typeof finding.fixedVersion === "string" && finding.fixedVersion.length > 0,
  }
}

function compareGroups(left, right) {
  var findingOrder = compareFindings(left.findings[0], right.findings[0])
  if (findingOrder !== 0) return findingOrder
  return compareText(left.watchTarget, right.watchTarget)
}

function compareFindings(left, right) {
  if (left.knownExploited !== right.knownExploited) return left.knownExploited ? -1 : 1
  var severityOrder = SEVERITIES.indexOf(left.severity) - SEVERITIES.indexOf(right.severity)
  if (severityOrder !== 0) return severityOrder
  if (left.hasFixedVersion !== right.hasFixedVersion) return left.hasFixedVersion ? -1 : 1
  return compareText(left.advisoryId, right.advisoryId)
}

function versionText(finding) {
  var installed = valueOr(finding.installedVersion, "Installed version not recorded")
  if (typeof finding.fixedVersion === "string" && finding.fixedVersion.length > 0) {
    return "Installed " + presentationText(installed) + "; fixed in " + presentationText(finding.fixedVersion)
  }
  return "Installed " + presentationText(installed) + "; no fixed version reported"
}

function kevText(status) {
  switch (status) {
  case "listed": return "The matched CVE is listed in the CISA Known Exploited Vulnerabilities Catalog for prioritization."
  case "not_listed": return "The CVE is not listed in the current catalog data."
  default: return "KEV listing status is unknown or unavailable."
  }
}

function coverage(label, source, currentTime) {
  if (isCurrent(source, currentTime)) return coverageState(label + ": current", source, currentTime)
  if (source && source.status === "stale") return coverageState(label + ": last known", source, currentTime)
  if (source && source.status === "not_applicable") return coverageState(label + ": not applicable", source, currentTime)
  return coverageState(label + ": unavailable or incompatible", source, currentTime)
}

function coverageState(text, source, currentTime) {
  return { text: text, ageText: ageText(source ? source.observedAt : null, currentTime) }
}

function ageText(value, currentTime) {
  var observed = typeof value === "string" ? Date.parse(value) : NaN
  if (isNaN(observed) || typeof currentTime !== "number" || !isFinite(currentTime)) return "age not recorded"
  var seconds = Math.max(0, Math.floor((currentTime - observed) / 1000))
  if (seconds < 60) return plural(seconds, "second") + " ago"
  var minutes = Math.floor(seconds / 60)
  if (minutes < 60) return plural(minutes, "minute") + " ago"
  var hours = Math.floor(minutes / 60)
  if (hours < 24) return plural(hours, "hour") + " ago"
  return plural(Math.floor(hours / 24), "day") + " ago"
}

function sourceFor(values, name) {
  return values.filter(function(value) { return value && value.source === name })[0] || null
}

function isCurrent(source, currentTime) {
  return source && source.status === "ok" && CURRENT_PROVENANCES.indexOf(source.provenance) !== -1 && sourceFresh(source, currentTime)
}
function isRetainedOrCurrent(source, currentTime) {
  return isCurrent(source, currentTime) || (source && source.status === "stale" && source.provenance === "last_good")
}
function sourceFresh(source, currentTime) {
  var freshUntil = typeof source.freshUntil === "string" ? Date.parse(source.freshUntil) : NaN
  return !isNaN(freshUntil) && typeof currentTime === "number" && isFinite(currentTime) && freshUntil > currentTime
}
function validGroup(group) { return group && typeof group.itemId === "string" && group.itemId.indexOf("arch:") === 0 && Array.isArray(group.findings) }
function validFinding(finding) { return finding && canonicalAverage(finding.id) && finding.advisoryId === finding.id && Array.isArray(finding.cveIds) && typeof finding.severity === "string" && SEVERITIES.indexOf(finding.severity) !== -1 }
function canonicalAverage(value) { return typeof value === "string" && /^AVG-[0-9]+$/.test(value) }
function canonicalCve(value) { return typeof value === "string" && /^CVE-[0-9]{4}-[0-9]{4,}$/.test(value) }
function presentationText(value) {
  var text = value === null || value === undefined ? "Not recorded" : String(value)
  text = text.replace(/[\u0000-\u001f\u007f-\u009f]/g, " ")
  return text.length > MAX_PRESENTATION_LENGTH ? text.slice(0, MAX_PRESENTATION_LENGTH - 1) + "…" : text
}
function compareText(left, right) { return left < right ? -1 : (left > right ? 1 : 0) }
function valueOr(value, fallback) { return typeof value === "string" && value.length > 0 ? value : fallback }
function plural(value, unit) { return value + " " + unit + (value === 1 ? "" : "s") }
