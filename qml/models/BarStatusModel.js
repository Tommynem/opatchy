.pragma library

var MANDATORY_SOURCES = ["security", "omarchy", "arch"]

function status(snapshot, refreshing, serviceAvailable) {
  if (!serviceAvailable) return view("unavailable", "?", "", false, false, refreshing === true, counts(null), "Opatchy service unavailable. Open the panel to review setup.")

  var payload = snapshot && snapshot.payload ? snapshot.payload : null
  if (!payload) return view("degraded", "?", "", false, false, refreshing === true, counts(null), "Opatchy has no validated source result yet.")

  var values = counts(payload)
  var urgent = urgentSecurityCount(payload.findings)
  var mandatory = mandatoryDegradationCount(payload.sources)
  var degraded = Math.max(values.degraded, mandatory)
  var stale = staleSourceCount(payload.sources) > 0
  var selected = urgent > 0
    ? view("security", "!", String(urgent), true, stale, refreshing === true, values, "")
    : (values.watched > 0
      ? view("watched", "*", String(values.watched), false, stale, refreshing === true, values, "")
      : (values.updates > 0
        ? view("updates", "^", String(values.updates), false, stale, refreshing === true, values, "")
        : (degraded > 0
          ? view("degraded", stale ? "~" : "?", String(degraded), false, stale, refreshing === true, values, "")
          : view("clear", "O", "", false, false, refreshing === true, values, ""))))
  selected.tooltip = tooltip(selected, urgent, degraded)
  return selected
}

function view(kind, glyph, badge, active, stale, spinner, values, tooltipText) {
  var label = glyph + badge + (stale ? " ~" : "") + (spinner ? " …" : "")
  return { kind: kind, glyph: glyph, badge: badge, active: active, stale: stale, spinner: spinner, label: label, tooltip: tooltipText, counts: values }
}

function tooltip(selected, urgent, degraded) {
  var values = selected.counts
  var text = values.security + " security findings; " + urgent + " high or critical; "
    + values.watched + " watched updates; " + values.updates + " other updates; "
    + degraded + " sources need attention."
  if (selected.stale) text += " Last known data is shown for at least one source."
  if (selected.spinner) text += " Refreshing source scan."
  return text
}

function counts(payload) {
  var summary = payload && payload.summary ? payload.summary : {}
  var watched = number(summary.watchedUpdates)
  var total = number(summary.totalUpdates)
  return { security: number(summary.securityFindings), watched: watched, updates: Math.max(0, total - watched), degraded: number(summary.degradedSources) }
}

function urgentSecurityCount(groups) {
  if (!isList(groups)) return 0
  var count = 0
  for (var index = 0; index < groups.length; index += 1) {
    var findings = groups[index] && isList(groups[index].findings) ? groups[index].findings : []
    for (var findingIndex = 0; findingIndex < findings.length; findingIndex += 1) {
      var severity = findings[findingIndex] ? findings[findingIndex].severity : ""
      if (severity === "high" || severity === "critical") count += 1
    }
  }
  return count
}

function mandatoryDegradationCount(sources) {
  if (!isList(sources)) return 0
  var count = 0
  for (var index = 0; index < sources.length; index += 1) {
    var source = sources[index]
    if (source && MANDATORY_SOURCES.indexOf(source.source) !== -1 && source.status !== "ok") count += 1
  }
  return count
}

function staleSourceCount(sources) {
  if (!isList(sources)) return 0
  var count = 0
  for (var index = 0; index < sources.length; index += 1)
    if (sources[index] && sources[index].status === "stale") count += 1
  return count
}

function number(value) { return typeof value === "number" && isFinite(value) && value >= 0 ? value : 0 }
function isList(value) { return value !== null && value !== undefined && typeof value.length === "number" }
