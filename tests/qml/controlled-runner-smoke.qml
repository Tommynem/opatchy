import QtQuick
import Quickshell

ShellRoot {
  Item {
    id: root

    property string helperEntrypoint: Quickshell.env("OPATCHY_CONTROLLED_HELPER")
    property string sourceDir: Quickshell.env("OPATCHY_TEST_ROOT")
    property string mode: Quickshell.env("OPATCHY_CONTROLLED_MODE")
    property int interruptionCount: Number(Quickshell.env("OPATCHY_INTERRUPTION_COUNT"))
    property int interruption: 0
    property var transport: null

    function fail(message) {
      console.error("controlled-runner-smoke: " + message)
      Qt.exit(1)
    }

    function launch() {
      var component = Qt.createComponent("file://" + sourceDir + "/qml/models/HelperTransport.qml")
      if (component.status !== Component.Ready) {
        fail(component.errorString())
        return
      }
      transport = component.createObject(root, {
        "helperEntrypoint": helperEntrypoint,
        "timeoutMs": mode === "timeout" ? 100 : 120000
      })
      if (transport === null || !transport.run({ "id": interruption, "argv": [] })) {
        fail("transport did not start")
        return
      }
      actionTimer.restart()
    }

    Component.onCompleted: {
      if (helperEntrypoint === "" || sourceDir === "" || ["stop", "timeout", "destroy"].indexOf(mode) === -1 || interruptionCount < 1) {
        fail("required controlled-runner environment is unavailable")
        return
      }
      launch()
    }

    Timer {
      id: actionTimer
      interval: root.mode === "timeout" ? 400 : 200
      repeat: false
      onTriggered: {
        if (root.mode === "stop") root.transport.stop()
        else if (root.mode === "destroy") root.transport.destroy()
        if (root.mode === "timeout") root.transport.destroy()
        root.transport = null
        if (root.interruption + 1 < root.interruptionCount) {
          root.interruption += 1
          restartTimer.restart()
          return
        }
        exitTimer.restart()
      }
    }

    Timer {
      id: restartTimer
      interval: 20
      repeat: false
      onTriggered: root.launch()
    }

    Timer {
      id: exitTimer
      interval: 300
      repeat: false
      onTriggered: Qt.exit(0)
    }
  }
}
