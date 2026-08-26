.pragma library

var PAGE_SIZE = 100
var MAX_QUERY_LENGTH = 128
var MAX_PRESENTATION_LENGTH = 256

function updateRows(snapshot, tab) {
  var source = sourceForTab(tab)
  if (source === null || !snapshot || !snapshot.payload || !Array.isArray(snapshot.payload.items)) return []
  var health = sourceHealth(snapshot, source)
  return snapshot.payload.items.filter(function(item) {
    return validItem(item) && item.source === source && typeof item.candidate === "string" && item.candidate.length > 0
  }).map(function(item) { return row(item, health) })
}

function canBrowse(tab) { return inventorySourceForTab(tab) !== null }

function inventoryRequest(tab, query, offset) {
  var source = inventorySourceForTab(tab)
  return inventoryRequestForSource(source, query, offset)
}

function inventoryRequestForSource(source, query, offset) {
  if (["arch", "aur", "flatpak", "mise"].indexOf(source) === -1) return null
  return { source: source, query: boundedQuery(query), limit: PAGE_SIZE, offset: boundedOffset(offset) }
}

function inventoryState(response, source, generationId) {
  if (!response) return { kind: "empty", rows: [], total: 0, summaryText: "Browse cached packages and tools." }
  if (!response.payload || response.payload.source !== source) {
    return { kind: "incompatible", rows: [], total: 0, summaryText: "Cached inventory is incompatible with this source." }
  }
  if (response.generationId !== generationId) {
    return { kind: "stale", rows: [], total: 0, summaryText: "Cached inventory is stale; newer source data is required." }
  }
  var items = Array.isArray(response.payload.items) ? response.payload.items : []
  var total = validCount(response.payload.total) ? response.payload.total : 0
  if (total < items.length || !items.every(validItem)) {
    return { kind: "incompatible", rows: [], total: 0, summaryText: "Cached inventory is incompatible with this source." }
  }
  return { kind: "ready", rows: items.map(function(item) { return row(item, "Cached inventory") }), total: total, summaryText: countText(total) }
}

function acceptInventory(current, received, source, generationId) {
  return inventoryState(received, source, generationId).kind === "ready" ? received : current
}

function footerActions(snapshot, tab, capabilities) {
  var items = snapshot && snapshot.payload && Array.isArray(snapshot.payload.items) ? snapshot.payload.items : []
  if (tab === "Flatpak") {
    return [
      action("flatpak-user", "Open update terminal (user)", hasFlatpakUpdate(items, "user") && capabilities.canOpenFlatpakUserUpdate === true),
      action("flatpak-system", "Open update terminal (system)", hasFlatpakUpdate(items, "system") && capabilities.canOpenFlatpakSystemUpdate === true),
    ]
  }
  var source = sourceForTab(tab)
  if (source === null) return []
  return [action("omarchy", "Open update terminal", hasUpdate(items, source) && capabilities.canOpenOmarchyUpdate === true)]
}

function sourceForTab(tab) {
  switch (tab) {
  case "Omarchy": return "omarchy"
  case "System": return "arch"
  case "AUR": return "aur"
  case "Flatpak": return "flatpak"
  case "mise": return "mise"
  default: return null
  }
}

function inventorySourceForTab(tab) {
  switch (tab) {
  case "System": return "arch"
  case "AUR": return "aur"
  case "Flatpak": return "flatpak"
  case "mise": return "mise"
  default: return null
  }
}

function sourceHealth(snapshot, source) {
  var sources = snapshot && snapshot.payload && Array.isArray(snapshot.payload.sources) ? snapshot.payload.sources : []
  var value = sources.filter(function(candidate) { return candidate && candidate.source === source })[0]
  var status = value && typeof value.status === "string" ? value.status : "invalid"
  return "Source health: " + healthText(status)
}

function row(item, context) {
  return {
    id: presentationText(item.id),
    identity: presentationText(item.source) + ":" + presentationText(item.id),
    label: presentationText(item.label),
    source: presentationText(item.source),
    installed: presentationText(item.installed),
    candidate: presentationText(item.candidate),
    watchText: item.watchable ? "Watch: " + presentationText(item.watchMode) : "Watch: unavailable",
    healthText: presentationText(context),
  }
}

function presentationText(value) {
  if (value === null || value === undefined) return "Not recorded"
  var text = String(value).replace(/[\u0000-\u001f\u007f-\u009f]/g, " ")
  return text.length > MAX_PRESENTATION_LENGTH ? text.slice(0, MAX_PRESENTATION_LENGTH - 1) + "…" : text
}

function boundedQuery(value) { return String(value || "").slice(0, MAX_QUERY_LENGTH) }
function boundedOffset(value) {
  var number = typeof value === "number" && isFinite(value) ? Math.floor(value) : 0
  return Math.max(0, Math.min(100000, number - (number % PAGE_SIZE)))
}
function validItem(value) {
  return value && typeof value === "object" && typeof value.id === "string" && typeof value.source === "string"
    && typeof value.label === "string" && (value.installed === null || typeof value.installed === "string")
    && (value.candidate === null || typeof value.candidate === "string") && typeof value.watchable === "boolean"
    && typeof value.watchMode === "string"
}
function validCount(value) { return typeof value === "number" && isFinite(value) && value >= 0 && Math.floor(value) === value }
function hasUpdate(items, source) { return items.some(function(item) { return validItem(item) && item.source === source && typeof item.candidate === "string" && item.candidate.length > 0 }) }
function hasFlatpakUpdate(items, scope) { return items.some(function(item) { return validItem(item) && item.source === "flatpak" && item.id.indexOf("flatpak:" + scope + ":") === 0 && typeof item.candidate === "string" && item.candidate.length > 0 }) }
function action(kind, text, enabled) { return { kind: kind, text: text, enabled: enabled } }
function countText(value) { return value === 0 ? "No cached packages match this query." : value === 1 ? "1 cached result." : value + " cached results." }
function healthText(status) {
  switch (status) {
  case "ok": return "Current"
  case "not_applicable": return "Not applicable"
  case "stale": return "Last known"
  case "invalid": return "Incompatible"
  default: return "Unavailable"
  }
}
