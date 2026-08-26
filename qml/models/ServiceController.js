.pragma library

var MAX_PROTOCOL_BYTES = 5 * 1024 * 1024
var INITIAL_SCAN_DELAY_MS = 30 * 1000
var POST_HANDOFF_SCAN_DELAY_MS = 10 * 60 * 1000
var RESPONSE_KINDS = ["snapshot", "inventory", "star-result", "error"]

function createController(options) {
  var controller = {}
  var queue = []
  var active = null
  var accepting = true
  var nextId = 1
  var refreshQueued = false
  var schedules = { initial: null, periodic: null, retry: null, handoff: null }
  var state = emptyState()

  function now() { return options.now() }
  function publish() {
    state = copy(state)
    controller.state = state
    options.onState(state)
  }
  function emptyState() {
    return {
      lastSnapshot: null, inventories: {}, lastStarResult: null, lastError: "",
      activeOperation: null, queuedOperations: 0, nextWakeAt: null
    }
  }
  function copy(value) {
    var next = {}
    for (var key in value) next[key] = value[key]
    return next
  }
  function updateQueueState() {
    state.activeOperation = active
    state.queuedOperations = queue.length
    state.nextWakeAt = earliestWake()
  }
  function earliestWake() {
    var earliest = null
    for (var key in schedules) {
      var due = schedules[key]
      if (due !== null && (earliest === null || due < earliest)) earliest = due
    }
    return earliest
  }
  function operation(kind, argv, expectedKind) {
    return { id: nextId++, kind: kind, argv: argv, expectedKind: expectedKind }
  }
  function enqueue(next) {
    queue.push(next)
    startNext()
  }
  function startNext() {
    if (!accepting || active || queue.length === 0) return
    active = queue.shift()
    if (active.kind === "scan") refreshQueued = false
    updateQueueState()
    publish()
    if (options.onStart(active) !== false) return
    state.lastError = "helper transport is unavailable"
    active = null
    updateQueueState()
    publish()
    startNext()
  }
  function setError(message) {
    state.lastError = message
  }
  function refresh() {
    if (!accepting || refreshQueued) return false
    refreshQueued = true
    enqueue(operation("scan", ["scan"], "snapshot"))
    return true
  }
  function due(scheduleName, at) {
    if (schedules[scheduleName] === null || schedules[scheduleName] > at) return false
    schedules[scheduleName] = null
    return true
  }
  function configureSnapshotSchedule(response) {
    var retry = earliestSourceRetry(response.payload.sources, now())
    schedules.retry = retry
    if (active && active.kind === "scan") {
      schedules.periodic = now() + jitteredInterval(options.refreshIntervalMs, options.random())
    }
  }
  function jitteredInterval(interval, random) {
    return Math.round(interval * (0.9 + random * 0.2))
  }
  function earliestSourceRetry(sources, current) {
    var earliest = null
    for (var index = 0; index < sources.length; index += 1) {
      var due = Date.parse(sources[index].freshUntil)
      if (isNaN(due) || due <= current) continue
      if (earliest === null || due < earliest) earliest = due
    }
    return earliest
  }
  function finishActive() {
    active = null
    updateQueueState()
    publish()
    startNext()
  }
  function accept(response) {
    state.lastError = ""
    if (response.kind === "snapshot") {
      state.lastSnapshot = response
      configureSnapshotSchedule(response)
    } else if (response.kind === "inventory") {
      var inventories = copy(state.inventories)
      inventories[response.payload.source] = response
      state.inventories = inventories
    } else if (response.kind === "star-result") {
      state.lastStarResult = response
    }
    options.onResponse(active, response)
  }

  controller.start = function() {
    if (!accepting) return
    schedules.initial = now() + INITIAL_SCAN_DELAY_MS
    enqueue(operation("snapshot", ["snapshot"], "snapshot"))
    updateQueueState()
    publish()
  }
  controller.requestRefresh = refresh
  controller.requestInventory = function(request) {
    if (!validInventoryRequest(request)) return false
    enqueue(operation("inventory", [
      "inventory", "--source", request.source, "--query", request.query,
      "--limit", String(request.limit), "--offset", String(request.offset)
    ], "inventory"))
    return true
  }
  controller.setStar = function(request) {
    if (!validStarRequest(request)) return false
    enqueue(operation("set-star", [
      "set-star", "--item-id", request.itemId, "--mode", request.mode
    ], "star-result"))
    return true
  }
  controller.wake = function(at) {
    if (!accepting) return
    var shouldRefresh = due("initial", at) || due("periodic", at)
    shouldRefresh = due("retry", at) || shouldRefresh
    shouldRefresh = due("handoff", at) || shouldRefresh
    if (shouldRefresh) refresh()
    updateQueueState()
    publish()
  }
  controller.schedulePostHandoffScan = function(at) {
    if (!accepting) return
    schedules.handoff = at + POST_HANDOFF_SCAN_DELAY_MS
    updateQueueState()
    publish()
  }
  controller.complete = function(operationId, result) {
    if (!accepting || !active || active.id !== operationId) return
    var completed = active
    if (result.timedOut === true) {
      setError("helper operation timed out")
    } else if (result.outputTooLarge === true || utf8Length(result.stdout) >= MAX_PROTOCOL_BYTES) {
      setError("helper output exceeded the five MiB limit")
    } else if (result.exitCode !== 0) {
      setError("helper exited with status " + result.exitCode)
    } else {
      var parsed = parseResponse(result.stdout)
      if (!parsed.ok) {
        setError(parsed.error)
      } else if (parsed.value.kind === "error") {
        setError(parsed.value.error.code + ": " + parsed.value.error.message)
      } else if (parsed.value.kind !== completed.expectedKind) {
        setError("helper response kind does not match the operation")
      } else {
        accept(parsed.value)
      }
    }
    finishActive()
  }
  controller.shutdown = function() {
    accepting = false
    queue = []
    active = null
    refreshQueued = false
    schedules = { initial: null, periodic: null, retry: null, handoff: null }
    updateQueueState()
    publish()
  }
  controller.state = state
  return controller
}

function parseResponse(text) {
  if (typeof text !== "string") return failure("helper output is not text")
  var value
  try {
    value = JSON.parse(text)
  } catch (error) {
    return failure("helper output is not valid JSON")
  }
  if (!isObject(value) || !exactEnvelope(value)) return failure("helper response envelope is invalid")
  if (value.protocolVersion !== 1) return failure("helper protocol version is unsupported")
  if (RESPONSE_KINDS.indexOf(value.kind) === -1) return failure("helper response kind is unsupported")
  if (!timestamp(value.generatedAt) || typeof value.generationId !== "string") return failure("helper response metadata is invalid")
  if (value.kind === "error") return validError(value) ? success(value) : failure("helper error response is invalid")
  if (value.kind === "snapshot") return validSnapshot(value) ? success(value) : failure("helper snapshot is invalid")
  if (value.kind === "inventory") return validInventory(value) ? success(value) : failure("helper inventory is invalid")
  return validStarResult(value) ? success(value) : failure("helper star result is invalid")
}

function exactEnvelope(value) {
  var keys = value.kind === "error"
    ? ["protocolVersion", "kind", "generatedAt", "generationId", "error"]
    : ["protocolVersion", "kind", "generatedAt", "generationId", "payload"]
  return exactKeys(value, keys)
}

function validSnapshot(value) {
  var payload = value.payload
  if (!isObject(payload) || !exactKeys(payload, ["scanState", "sources", "summary", "items", "findings", "notifications"])) return false
  if (typeof payload.scanState !== "string" || !Array.isArray(payload.sources) || !Array.isArray(payload.items) || !Array.isArray(payload.findings) || !Array.isArray(payload.notifications)) return false
  if (!isObject(payload.summary)) return false
  return validSummary(payload.summary) && payload.sources.every(validSource)
}

function validSummary(value) {
  var keys = ["totalUpdates", "watchedUpdates", "securityFindings", "degradedSources"]
  if (!exactKeys(value, keys)) return false
  return keys.every(function(key) { return nonnegativeInteger(value[key]) })
}

function validSource(value) {
  var allowed = ["source", "status", "provenance", "observedAt", "freshUntil", "cause", "scopes"]
  if (!isObject(value) || !allowedKeys(value, allowed)) return false
  var required = ["source", "status", "provenance", "observedAt", "freshUntil", "cause"]
  if (!required.every(function(key) { return key in value })) return false
  if (typeof value.source !== "string" || typeof value.status !== "string" || typeof value.provenance !== "string") return false
  if (!timestamp(value.observedAt) || !timestamp(value.freshUntil)) return false
  return !("scopes" in value) || Array.isArray(value.scopes)
}

function validInventory(value) {
  var payload = value.payload
  return isObject(payload) && exactKeys(payload, ["source", "total", "items"])
    && typeof payload.source === "string" && nonnegativeInteger(payload.total) && Array.isArray(payload.items)
}

function validStarResult(value) {
  var payload = value.payload
  return isObject(payload) && exactKeys(payload, ["itemId", "mode"])
    && typeof payload.itemId === "string" && ["off", "temporary", "permanent"].indexOf(payload.mode) !== -1
}

function validError(value) {
  return isObject(value.error) && exactKeys(value.error, ["code", "message"])
    && typeof value.error.code === "string" && typeof value.error.message === "string"
}

function validInventoryRequest(value) {
  return isObject(value) && typeof value.source === "string" && typeof value.query === "string"
    && nonnegativeInteger(value.offset) && nonnegativeInteger(value.limit) && value.limit > 0
}

function validStarRequest(value) {
  return isObject(value) && typeof value.itemId === "string" && value.itemId.length > 0
    && ["off", "temporary", "permanent"].indexOf(value.mode) !== -1
}

function timestamp(value) {
  return typeof value === "string" && value.length >= 21 && value.charAt(10) === "T"
    && value.charAt(value.length - 1) === "Z" && !isNaN(Date.parse(value))
}

function exactKeys(value, keys) {
  return allowedKeys(value, keys) && Object.keys(value).length === keys.length
}

function allowedKeys(value, keys) {
  return Object.keys(value).every(function(key) { return keys.indexOf(key) !== -1 })
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

function nonnegativeInteger(value) {
  return typeof value === "number" && isFinite(value) && Math.floor(value) === value && value >= 0
}

function utf8Length(value) {
  var length = 0
  for (var index = 0; index < value.length; index += 1) {
    var code = value.charCodeAt(index)
    if (code < 0x80) length += 1
    else if (code < 0x800) length += 2
    else if (code >= 0xd800 && code <= 0xdbff && index + 1 < value.length
      && value.charCodeAt(index + 1) >= 0xdc00 && value.charCodeAt(index + 1) <= 0xdfff) {
      length += 4
      index += 1
    } else length += 3
  }
  return length
}

function success(value) { return { ok: true, value: value } }
function failure(error) { return { ok: false, error: error } }
