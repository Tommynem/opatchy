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
    if (active.kind === "scan") refreshQueued = false
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
    state.lastFailureOperation = completed ? operationIdentity(completed) : null
  }
  function refresh() {
    if (!accepting || refreshQueued) return false
    refreshQueued = true
    enqueue(operation("scan", ["scan"], "snapshot"))
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
    var argv = [
      "set-star", "--item-id", request.itemId, "--mode", request.mode
    ]
    if (hasSecurityWatchRequest(request)) {
      argv = argv.concat([
        "--security-advisory", request.securityAdvisory,
        "--fixed-version", request.fixedVersion,
        "--cve-ids", request.cveIds.join(",")
      ])
    }
    var next = operation("set-star", argv, "star-result")
    next.itemId = request.itemId
    next.mode = request.mode
    if (hasSecurityWatchRequest(request)) {
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
    schedules = { initial: null, periodic: null, retry: null, handoff: null }
    updateQueueState()
    publish()
  }
  controller.state = state
  return controller
}
function isObject(value) { return value !== null && typeof value === "object" && !Array.isArray(value) }
function nonnegativeInteger(value) { return typeof value === "number" && isFinite(value) && Math.floor(value) === value && value >= 0 }
function validInventoryRequest(value) {
  return isObject(value) && ["arch", "aur", "flatpak", "mise"].indexOf(value.source) !== -1 && typeof value.query === "string" && value.query.length <= 128 && nonnegativeInteger(value.offset) && value.offset <= 100000 && nonnegativeInteger(value.limit) && value.limit >= 1 && value.limit <= 100
}
function validStarRequest(value) {
  return isObject(value) && typeof value.itemId === "string" && value.itemId.length > 0 && value.itemId.length <= 128 && ["off", "temporary", "permanent"].indexOf(value.mode) !== -1 && validSecurityWatchRequest(value)
}
function operationIdentity(value) {
  var identity = { id: value.id, kind: value.kind, itemId: value.itemId, mode: value.mode }
  if (hasSecurityWatchRequest(value)) {
    identity.securityAdvisory = value.securityAdvisory; identity.fixedVersion = value.fixedVersion; identity.cveIds = value.cveIds.slice()
  }
  return identity
}
function hasSecurityWatchRequest(value) { return value.securityAdvisory !== undefined }
function validSecurityWatchRequest(value) {
  var fields = ["securityAdvisory", "fixedVersion", "cveIds"], present = fields.filter(function(field) { return value[field] !== undefined }).length
  if (present === 0) return true
  if (present !== fields.length || value.mode !== "temporary" || !/^arch:[A-Za-z0-9@_+][A-Za-z0-9@._+-]{0,127}$/.test(value.itemId)) return false
  if (typeof value.securityAdvisory !== "string" || !/^AVG-[0-9]{1,120}$/.test(value.securityAdvisory) || typeof value.fixedVersion !== "string" || !/^[\x20-\x7e]{1,256}$/.test(value.fixedVersion) || !Array.isArray(value.cveIds) || value.cveIds.length === 0 || value.cveIds.length > 16) return false
  for (var index = 0; index < value.cveIds.length; index += 1) if (typeof value.cveIds[index] !== "string" || !/^CVE-[0-9]{4}-[0-9]{4,19}$/.test(value.cveIds[index]) || value.cveIds.indexOf(value.cveIds[index]) !== index) return false
  return true
}
