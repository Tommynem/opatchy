.pragma library

var INITIAL_SCAN_DELAY_MS = 30 * 1000
var POST_HANDOFF_SCAN_DELAY_MS = 10 * 60 * 1000

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
    } else if (result.outputTooLarge === true) {
      setError("helper output exceeded the five MiB limit")
    } else if (result.exitCode !== 0) {
      setError("helper exited with status " + result.exitCode)
    } else {
      var parsed = options.parseResponse(result.stdout)
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

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

function nonnegativeInteger(value) {
  return typeof value === "number" && isFinite(value) && Math.floor(value) === value && value >= 0
}

function validInventoryRequest(value) {
  return isObject(value) && ["arch", "aur", "flatpak", "mise"].indexOf(value.source) !== -1
    && typeof value.query === "string" && value.query.length <= 128 && nonnegativeInteger(value.offset)
    && value.offset <= 100000 && nonnegativeInteger(value.limit) && value.limit >= 1 && value.limit <= 100
}

function validStarRequest(value) {
  return isObject(value) && typeof value.itemId === "string" && value.itemId.length > 0 && value.itemId.length <= 128
    && ["off", "temporary", "permanent"].indexOf(value.mode) !== -1
}
