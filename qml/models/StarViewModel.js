.pragma library

var MODES = ["off", "temporary", "permanent"]

function presentation(mode, notifyPermanent, watchable, lastKnown) {
  var normalized = MODES.indexOf(mode) === -1 ? "off" : mode
  var result = modePresentation(normalized, notifyPermanent === true, watchable === true)
  if (lastKnown === true && normalized !== "off") {
    result.label += " (last-known)"
    result.tooltip += " This is last-known data."
  }
  return result
}

function modePresentation(mode, notifyPermanent, watchable) {
  switch (mode) {
  case "off":
    return watchable
      ? state("off", "temporary", "☆", "Not watched", "Not watched. Watch until one observed update installs.", "Not watched; activate temporary watch", true)
      : state("off", null, "☆", "Not watched", "Not watched. This unavailable item cannot start a watch.", "Not watched; unavailable item", false)
  case "temporary":
    return state("temporary", "permanent", "◌", "Watching until one observed update installs", "Temporary watch. It clears only after one observed update installs.", "Temporary watch; activate permanent watch", true)
  case "permanent":
    return state("permanent", "off", "★", notifyPermanent ? "Watching permanently with notifications" : "Watching permanently; notifications disabled in settings", notifyPermanent ? "Permanent watch with notifications. Clear this watch." : "Permanent watch; notifications are disabled in settings. Clear this watch.", notifyPermanent ? "Permanent watch with notifications; clear watch" : "Permanent watch; notifications disabled in settings; clear watch", true)
  }
  return state("off", null, "☆", "Not watched", "Not watched.", "Not watched", false)
}

function state(mode, nextMode, glyph, label, tooltip, accessibleName, enabled) {
  var shortLabel = mode === "off" ? "Off" : (mode === "temporary" ? "One update" : "Always")
  return { mode: mode, nextMode: nextMode, glyph: glyph, label: label, shortLabel: shortLabel, tooltip: tooltip, accessibleName: accessibleName, enabled: enabled }
}

function watchedRows(rows) {
  if (!Array.isArray(rows)) return []
  return rows.filter(function(row) {
    return row && (row.mode === "temporary" || row.mode === "permanent")
  }).map(function(row) {
    return { target: row.target, mode: row.mode, watchable: row.watchable === true, label: row.label, missing: row.watchable === false && row.mode === "permanent" }
  })
}
