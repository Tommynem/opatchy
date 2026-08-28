import QtQuick
import "qml/models/ActionPolicy.js" as ActionPolicy
import "qml/models/ServiceController.js" as ServiceController
import "qml/models/ProtocolValidator.js" as ProtocolValidator
import "qml/models" as Models

Item {
  id: root

  property var shell: null
  property var manifest: null
  property int helperTimeoutMs: 120000
  readonly property string sourceDir: manifest && typeof manifest.__sourceDir === "string"
    ? manifest.__sourceDir
    : ""
  readonly property string helperEntrypoint: localPath(sourceDir) === ""
    ? ""
    : localPath(sourceDir) + "/helper/opatchy.py"
  property var _controller: null
  property bool _readyForInitialization: false
  property var handoffTransport: terminalHandoff
  property var _updateAllActions: []
  property bool _updateAllActive: false
  property var _state: ({
    "lastSnapshot": null,
    "inventories": {},
    "lastStarResult": null,
    "lastError": "",
    "lastFailureKind": "",
    "lastFailureOperation": null,
    "lastAttemptAt": null,
    "lastSuccessAt": null,
    "handoffAt": null,
    "activeOperation": null,
    "queuedOperations": 0,
    "refreshing": false,
    "nextWakeAt": null
  })

  readonly property var lastSnapshot: _state.lastSnapshot
  readonly property var inventories: _state.inventories
  readonly property var lastStarResult: _state.lastStarResult
  readonly property string lastError: _state.lastError
  readonly property string lastFailureKind: _state.lastFailureKind
  readonly property var lastFailureOperation: _state.lastFailureOperation
  readonly property var lastAttemptAt: _state.lastAttemptAt
  readonly property var lastSuccessAt: _state.lastSuccessAt
  readonly property var handoffAt: _state.handoffAt
  readonly property var activeOperation: _state.activeOperation
  readonly property int queuedOperations: _state.queuedOperations
  readonly property bool refreshing: _state.refreshing
  readonly property var nextWakeAt: _state.nextWakeAt
  readonly property var sources: lastSnapshot ? lastSnapshot.payload.sources : []
  readonly property var summary: lastSnapshot ? lastSnapshot.payload.summary : null
  readonly property var items: lastSnapshot ? lastSnapshot.payload.items : []
  readonly property var findings: lastSnapshot ? lastSnapshot.payload.findings : []
  readonly property var notifications: lastSnapshot ? lastSnapshot.payload.notifications : []
  readonly property bool busy: activeOperation !== null
  readonly property var actionCapabilities: handoffTransport && handoffTransport.capabilities
    ? handoffTransport.capabilities
    : ({ "launcher": false, "omarchyUpdate": false, "flatpak": false })
  readonly property bool canOpenOmarchyUpdate: canOpenAction("omarchy")
  readonly property bool canOpenFlatpakUserUpdate: canOpenAction("flatpak-user")
  readonly property bool canOpenFlatpakSystemUpdate: canOpenAction("flatpak-system")
  readonly property bool canUpdateAll: handoffTransport && handoffTransport.finished !== undefined && !_updateAllActive && !handoffTransport.running
    && ActionPolicy.eligibleUpdateActions(lastSnapshot, actionCapabilities).length > 0

  signal snapshotChanged(var snapshot)
  signal inventoryChanged(string source, var inventory, var operation)
  signal starResultChanged(var result, var operation)
  signal starFailed(var operation, string message)
  signal operationFailed(string message)
  signal handoffStarted(double handoffAt)

  function localPath(value) {
    if (value.indexOf("file://") !== 0) return value
    return decodeURIComponent(value.substring(7))
  }

  function requestRefresh() {
    return _controller ? _controller.requestRefresh() : false
  }

  function requestInventory(request) {
    return _controller ? _controller.requestInventory(request) : false
  }

  function setStar(request) {
    return _controller ? _controller.setStar(request) : false
  }

  function schedulePostHandoffScan() {
    if (_controller) _controller.schedulePostHandoffScan(Date.now())
  }

  function canOpenAction(name) {
    return handoffTransport && !handoffTransport.running
      && ActionPolicy.isEligible(lastSnapshot, name, actionCapabilities)
  }

  function openOmarchyUpdate() {
    return openAction("omarchy")
  }

  function openFlatpakUserUpdate() {
    return openAction("flatpak-user")
  }

  function openFlatpakSystemUpdate() {
    return openAction("flatpak-system")
  }

  function requestUpdateAll() {
    if (!canUpdateAll) return false
    _updateAllActions = ActionPolicy.UPDATE_ALL_ACTIONS.slice()
    _updateAllActive = true
    startNextUpdateAll()
    return true
  }

  function openAction(name) {
    var action = ActionPolicy.actionFor(name)
    if (action === null || !canOpenAction(name)) return false
    if (handoffTransport.start(action.name)) return true
    reportHandoffFailure("Open update terminal is unavailable")
    return false
  }

  function recordHandoff() {
    if (!_controller) return
    _controller.recordHandoff(Date.now())
    handoffStarted(handoffAt)
  }

  function startNextUpdateAll() {
    if (!_updateAllActive || !handoffTransport || handoffTransport.running) return
    while (_updateAllActions.length > 0) {
      var actionName = _updateAllActions.shift()
      if (!ActionPolicy.isEligible(lastSnapshot, actionName, actionCapabilities)) continue
      if (openAction(actionName)) return
      finishUpdateAll()
      return
    }
    finishUpdateAll()
  }

  function finishUpdateAll() {
    _updateAllActions = []
    _updateAllActive = false
  }

  function handleHandoffFinished(exitCode) {
    if (!_updateAllActive) return
    if (exitCode !== 0) {
      finishUpdateAll()
      reportHandoffFailure()
      return
    }
    startNextUpdateAll()
  }

  function reportHandoffFailure() {
    var message = "Open update terminal could not be started"
    _state = Object.assign({}, _state, { "lastError": message })
    operationFailed(message)
  }

  function bindHandoffTransport() {
    if (!handoffTransport || !handoffTransport.started || !handoffTransport.failed) return
    handoffTransport.started.connect(recordHandoff)
    handoffTransport.failed.connect(function() {
      finishUpdateAll()
      reportHandoffFailure()
    })
    if (handoffTransport.finished) handoffTransport.finished.connect(handleHandoffFinished)
  }

  function applyState(state) {
    _state = state
    armWakeTimer()
  }

  function applyResponse(operation, response) {
    if (response.kind === "snapshot") snapshotChanged(response)
    else if (response.kind === "inventory") inventoryChanged(response.payload.source, response, operation)
    else if (response.kind === "star-result") starResultChanged(response, operation)
  }

  function startOperation(operation) {
    return transport.run(operation)
  }

  function armWakeTimer() {
    if (nextWakeAt === null) {
      wakeTimer.stop()
      return
    }
    wakeTimer.interval = Math.max(0, nextWakeAt - Date.now())
    wakeTimer.restart()
  }

  function initializeController() {
    if (_controller) return
    if (helperEntrypoint === "") {
      _state = Object.assign({}, _state, { "lastError": "trusted helper path is unavailable" })
      return
    }
    _state = Object.assign({}, _state, { "lastError": "" })
    _controller = ServiceController.createController({
      now: function() { return Date.now() },
      random: function() { return Math.random() },
      refreshIntervalMs: 21600 * 1000,
      onStart: function(operation) { return root.startOperation(operation) },
      onState: function(state) { root.applyState(state) },
      onResponse: function(operation, response) { root.applyResponse(operation, response) },
      parseResponse: ProtocolValidator.parseResponse
    })
    _controller.start()
  }

  Models.HelperTransport {
    id: transport
    helperEntrypoint: root.helperEntrypoint
    timeoutMs: root.helperTimeoutMs
    onCompleted: function(operation, result) {
      if (root._controller) root._controller.complete(operation.id, result)
      if (operation.kind === "set-star" && root.lastFailureOperation && root.lastFailureOperation.id === operation.id)
        root.starFailed(root.lastFailureOperation, root.lastError)
      else if (root.lastError !== "") root.operationFailed(root.lastError)
    }
  }

  Models.TerminalHandoff {
    id: terminalHandoff
  }

  Timer {
    id: wakeTimer
    repeat: false
    onTriggered: {
      if (root._controller) root._controller.wake(Date.now())
    }
  }

  Component.onCompleted: {
    bindHandoffTransport()
    _readyForInitialization = true
    initializeController()
  }

  onHelperEntrypointChanged: {
    if (_readyForInitialization) initializeController()
  }

  Component.onDestruction: {
    if (_controller) _controller.shutdown()
    transport.stop()
    wakeTimer.stop()
  }
}
