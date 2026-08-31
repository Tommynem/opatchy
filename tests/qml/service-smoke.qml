import QtQuick
import Quickshell

Item {
  id: root

  property string sourceDir: Quickshell.env("OPATCHY_TEST_ROOT")
  property var service: null
  property bool receivedSnapshot: false

  function fail(message) {
    console.error("service-smoke: " + message)
    Qt.exit(1)
  }

  function finish() {
    console.log("service-smoke: snapshot accepted; cancelling scan")
    if (service) service.destroy()
    Qt.exit(0)
  }

  Component.onCompleted: {
    if (sourceDir === "") {
      fail("OPATCHY_TEST_ROOT is required")
      return
    }
    var component = Qt.createComponent("file://" + sourceDir + "/Service.qml")
    if (component.status !== Component.Ready) {
      fail(component.errorString())
      return
    }
    service = component.createObject(root, {
      "manifest": { "id": "io.github.tommynem.opatchy", "__sourceDir": sourceDir }
    })
    if (service === null) {
      fail("Service.qml did not instantiate")
      return
    }
    service.snapshotChanged.connect(function(snapshot) {
      if (receivedSnapshot) return
      receivedSnapshot = true
      if (snapshot.generationId !== "fixture-snapshot") {
        fail("fixture snapshot was not published")
        return
      }
      if (!service.requestRefresh()) {
        fail("scan request was not accepted")
        return
      }
      cancellationTimer.start()
    })
  }

  Timer {
    id: cancellationTimer
    interval: 100
    repeat: false
    onTriggered: root.finish()
  }

  Timer {
    interval: 3000
    running: true
    repeat: false
    onTriggered: root.fail("fixture snapshot timed out")
  }
}
