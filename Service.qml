import QtQuick
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
  property var _state: ({
    "lastSnapshot": null,
    "inventories": {},
    "lastStarResult": null,
    "lastError": "",
    "activeOperation": null,
    "queuedOperations": 0,
    "nextWakeAt": null
  })

  readonly property var lastSnapshot: _state.lastSnapshot
  readonly property var inventories: _state.inventories
  readonly property var lastStarResult: _state.lastStarResult
  readonly property string lastError: _state.lastError
  readonly property var activeOperation: _state.activeOperation
  readonly property int queuedOperations: _state.queuedOperations
  readonly property var nextWakeAt: _state.nextWakeAt
  readonly property var sources: lastSnapshot ? lastSnapshot.payload.sources : []
  readonly property var summary: lastSnapshot ? lastSnapshot.payload.summary : null
  readonly property var items: lastSnapshot ? lastSnapshot.payload.items : []
  readonly property var findings: lastSnapshot ? lastSnapshot.payload.findings : []
  readonly property var notifications: lastSnapshot ? lastSnapshot.payload.notifications : []
  readonly property bool busy: activeOperation !== null

  signal snapshotChanged(var snapshot)
  signal inventoryChanged(string source, var inventory)
  signal starResultChanged(var result)
  signal operationFailed(string message)

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

  function applyState(state) {
    _state = state
    armWakeTimer()
  }

  function applyResponse(operation, response) {
    if (response.kind === "snapshot") snapshotChanged(response)
    else if (response.kind === "inventory") inventoryChanged(response.payload.source, response)
    else if (response.kind === "star-result") starResultChanged(response)
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

  Models.HelperTransport {
    id: transport
    helperEntrypoint: root.helperEntrypoint
    timeoutMs: root.helperTimeoutMs
    onCompleted: function(operation, result) {
      if (root._controller) root._controller.complete(operation.id, result)
      if (root.lastError !== "") root.operationFailed(root.lastError)
    }
  }

  Timer {
    id: wakeTimer
    repeat: false
    onTriggered: {
      if (root._controller) root._controller.wake(Date.now())
    }
  }

  Component.onCompleted: {
    if (helperEntrypoint === "") {
      _state = Object.assign({}, _state, { "lastError": "trusted helper path is unavailable" })
      return
    }
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

  Component.onDestruction: {
    if (_controller) _controller.shutdown()
    transport.stop()
    wakeTimer.stop()
  }
}
