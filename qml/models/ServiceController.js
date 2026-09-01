.pragma library
.import "RequestValidation.js" as RequestValidation

var INITIAL_SCAN_DELAY_MS = 30 * 1000
var POST_HANDOFF_SCAN_DELAY_MS = 10 * 60 * 1000
function createController(options) {
  var controller = {}
  var queue = []
  var active = null
  var accepting = true
  var nextId = 1
  var refreshQueued = false
  var queuedRefresh = null
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
      lastSnapshot: null, inventories: {}, lastStarResult: null, lastError: "", lastFailureKind: "", lastFailureOperation: null,
      lastAttemptAt: null, lastSuccessAt: null, handoffAt: null,
      activeOperation: null, queuedOperations: 0, refreshing: false, nextWakeAt: null
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
    state.refreshing = hasScanOperation()
    state.nextWakeAt = earliestWake()
  }
  function hasScanOperation() {
    if (active && active.kind === "scan") return true
    return queue.some(function(value) { return value.kind === "scan" })
  }
  function earliestWake() {
    var earliest = null
    for (var key in schedules) {
      var due = schedules[key]
      if (due !== null && (earliest === null || due < earliest)) earliest = due
    }
    return earliest
  }
  function operation(kind, argv, expectedKind) { return { id: nextId++, kind: kind, argv: argv, expectedKind: expectedKind } }
  function enqueue(next) {
    queue.push(next)
    if (active) {
      updateQueueState()
      publish()
      return
    }
    startNext()
  }
  function startNext() {
    if (!accepting || active || queue.length === 0) return
    active = queue.shift()
    if (active === queuedRefresh) {
      refreshQueued = false
      queuedRefresh = null
    }
    if (active.kind === "scan") state.lastAttemptAt = now()
    updateQueueState()
    publish()
    if (options.onStart(active) !== false) return
    recordFailure(active, "transport", "helper transport is unavailable")
    active = null
    updateQueueState()
    publish()
    startNext()
  }
  function setError(kind, message) { state.lastFailureKind = kind; state.lastError = message }
  function recordFailure(completed, kind, message) {
    setError(kind, message)
    state.lastFailureOperation = completed ? RequestValidation.operationIdentity(completed) : null
  }
  function scanArguments() {
    var provider = options.scanArguments
    var arguments = typeof provider === "function" ? provider() : provider
    return Array.isArray(arguments) ? arguments.slice() : []
  }
  function refresh(force) {
    if (!accepting) return false
    if (refreshQueued) {
      if (force && queuedRefresh.argv.indexOf("--force") === -1) queuedRefresh.argv.push("--force")
      return false
    }
    var arguments = scanArguments()
    var next = operation("scan", force ? ["scan", "--force"].concat(arguments) : ["scan"].concat(arguments), "snapshot")
    refreshQueued = true
    queuedRefresh = next
    enqueue(next)
    return true
  }
  function due(scheduleName, at) { if (schedules[scheduleName] === null || schedules[scheduleName] > at) return false; schedules[scheduleName] = null; return true }
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
    state.lastFailureKind = ""
    state.lastFailureOperation = null
    if (response.kind === "snapshot") {
      state.lastSnapshot = response
      state.lastSuccessAt = Date.parse(response.generatedAt)
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
  controller.requestRefresh = function() { return refresh(true) }
  controller.requestInventory = function(request) {
    if (!RequestValidation.validInventoryRequest(request)) return false
    enqueue(operation("inventory", [
      "inventory", "--source", request.source, "--query", request.query,
      "--limit", String(request.limit), "--offset", String(request.offset)
    ], "inventory"))
    return true
  }
  controller.setStar = function(request) {
    if (!RequestValidation.validStarRequest(request)) return false
    var argv = [
      "set-star", "--item-id", request.itemId, "--mode", request.mode
    ]
    if (RequestValidation.hasSecurityWatchRequest(request)) {
      argv = argv.concat([
        "--security-advisory", request.securityAdvisory,
        "--fixed-version", request.fixedVersion,
        "--cve-ids", request.cveIds.join(",")
      ])
    }
    var next = operation("set-star", argv, "star-result")
    next.itemId = request.itemId
    next.mode = request.mode
    if (RequestValidation.hasSecurityWatchRequest(request)) {
      next.securityAdvisory = request.securityAdvisory
      next.fixedVersion = request.fixedVersion
      next.cveIds = request.cveIds.slice()
    }
    enqueue(next)
    return true
  }
  controller.wake = function(at) {
    if (!accepting) return
    var shouldRefresh = due("initial", at) || due("periodic", at)
    shouldRefresh = due("retry", at) || shouldRefresh
    shouldRefresh = due("handoff", at) || shouldRefresh
    if (shouldRefresh) refresh(false)
    updateQueueState()
    publish()
  }
  controller.schedulePostHandoffScan = function(at) {
    if (!accepting) return
    schedules.handoff = at + POST_HANDOFF_SCAN_DELAY_MS
    updateQueueState()
    publish()
  }
  controller.recordHandoff = function(at) {
    if (!accepting) return
    state.handoffAt = at
    controller.schedulePostHandoffScan(at)
  }
  controller.complete = function(operationId, result) {
    if (!accepting || !active || active.id !== operationId) return
    var completed = active
    if (result.timedOut === true) {
      recordFailure(completed, "timeout", "helper operation timed out")
    } else if (result.outputTooLarge === true) {
      recordFailure(completed, "output", "helper output exceeded the five MiB limit")
    } else {
      var parsed = options.parseResponse(result.stdout)
      if (result.exitCode !== 0) {
        if (parsed.ok && parsed.value.kind === "error") {
          recordFailure(completed, "helper", parsed.value.error.code + ": " + parsed.value.error.message)
        } else {
          recordFailure(completed, "command", "helper exited with status " + result.exitCode)
        }
      } else if (!parsed.ok) {
        recordFailure(completed, "incompatible", parsed.error)
      } else if (parsed.value.kind === "error") {
        recordFailure(completed, "helper", parsed.value.error.code + ": " + parsed.value.error.message)
      } else if (parsed.value.kind !== completed.expectedKind) {
        recordFailure(completed, "incompatible", "helper response kind does not match the operation")
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
    queuedRefresh = null
    schedules = { initial: null, periodic: null, retry: null, handoff: null }
    updateQueueState()
    publish()
  }
  controller.state = state
  return controller
}
