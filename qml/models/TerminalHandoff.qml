import QtQml
import Quickshell.Io
import "ActionPolicy.js" as ActionPolicy

QtObject {
  id: root

  property bool launcherAvailable: false
  property bool omarchyUpdateAvailable: false
  property bool flatpakAvailable: false
  property int probeIndex: 0
  property bool pendingStart: false
  readonly property bool running: launcherProcess.running || pendingStart
  readonly property var capabilities: ({
    "launcher": launcherAvailable,
    "omarchyUpdate": omarchyUpdateAvailable,
    "flatpak": flatpakAvailable
  })

  signal started()
  signal failed(string message)

  function start(actionName) {
    if (running) return false
    var action = ActionPolicy.actionFor(actionName)
    if (action === null) return false
    pendingStart = true
    launcherProcess.command = action.argv
    launcherProcess.running = true
    return true
  }

  function probeNext() {
    switch (probeIndex) {
    case 0:
      probeProcess.command = ["/usr/bin/test", "-x", "/usr/bin/omarchy-launch-floating-terminal-with-presentation"]
      break
    case 1:
      probeProcess.command = ["/usr/bin/test", "-x", "/usr/bin/omarchy-update"]
      break
    case 2:
      probeProcess.command = ["/usr/bin/test", "-x", "/usr/bin/flatpak"]
      break
    default:
      return
    }
    probeProcess.running = true
  }

  function recordProbe(exitCode) {
    switch (probeIndex) {
    case 0:
      launcherAvailable = exitCode === 0
      break
    case 1:
      omarchyUpdateAvailable = exitCode === 0
      break
    case 2:
      flatpakAvailable = exitCode === 0
      break
    }
    probeIndex += 1
    probeNext()
  }

  property Process probeProcess: Process {
    onExited: function(exitCode) { root.recordProbe(exitCode) }
  }

  property Process launcherProcess: Process {
    onStarted: {
      if (!root.pendingStart) return
      root.pendingStart = false
      root.started()
    }
    onExited: function() {
      if (!root.pendingStart) return
      root.pendingStart = false
      root.failed("Open update terminal could not be started")
    }
  }

  Component.onCompleted: probeNext()
  Component.onDestruction: {
    if (probeProcess.running) probeProcess.running = false
    if (launcherProcess.running) launcherProcess.running = false
  }
}
