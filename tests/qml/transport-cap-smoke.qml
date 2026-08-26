import QtQuick
import Quickshell

ShellRoot {
  id: root

  property string sourceDir: Quickshell.env("OPATCHY_TEST_ROOT")
  property var transport: null

  function fail(message) {
    console.error("transport-cap-smoke: " + message)
    Qt.exit(1)
  }

  function run() {
    var component = Qt.createComponent("file://" + sourceDir + "/qml/models/HelperTransport.qml")
    if (component.status !== Component.Ready) {
      fail(component.errorString())
      return
    }
    transport = component.createObject(root)
    if (transport === null) {
      fail("HelperTransport.qml did not instantiate")
      return
    }
    transport.collectStderr("😀".repeat(4097))
    if (transport.stderrBytes !== 16 * 1024
      || transport.utf8Length(transport.stderrText) > 16 * 1024) {
      fail("stderr exceeded its UTF-8 byte cap")
      return
    }

    transport.collectStdout("€".repeat(1747626) + "aa")
    if (!transport.outputTooLarge || transport.stdoutBytes !== 5 * 1024 * 1024) {
      fail("stdout did not reject the exact five-MiB boundary")
      return
    }
    console.log("transport-cap-smoke: UTF-8 caps enforced")
    Qt.exit(0)
  }

  Component.onCompleted: capTimer.start()

  Timer {
    id: capTimer
    interval: 1
    repeat: false
    onTriggered: root.run()
  }
}
