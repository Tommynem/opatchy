import QtQuick
import Quickshell
import Quickshell.Io

ShellRoot {
  Item {
    id: root

    property string sourceDir: Quickshell.env("OPATCHY_TEST_ROOT")
    property var service: null
    property var launches: []
    property int stage: 0
    property bool failNext: false
    property double successfulHandoffAt: 0
    property string snapshotBeforeActions: ""

    function fail(message) {
      console.error("action-handoff-smoke: " + message)
      Qt.exit(1)
    }

    function check(condition, message) {
      if (!condition) fail(message)
    }

    function health(name) {
      var value = {
        "source": name,
        "status": "ok",
        "provenance": "live",
        "observedAt": "2026-08-26T00:00:00.000Z",
        "freshUntil": "2026-08-26T00:05:00.000Z",
        "cause": null
      }
      if (name === "flatpak") {
        value.scopes = ["user", "system"].map(function(scope) {
          return {
            "scope": scope,
            "status": "ok",
            "provenance": "live",
            "observedAt": "2026-08-26T00:00:00.000Z",
            "freshUntil": "2026-08-26T00:05:00.000Z",
            "cause": null
          }
        })
      }
      return value
    }

    function fixtureSnapshot() {
      return {
        "protocolVersion": 1,
        "kind": "snapshot",
        "generatedAt": "2026-08-26T00:00:00.000Z",
        "generationId": "action-handoff-fixture",
        "payload": {
          "scanState": "complete",
          "sources": [health("security"), health("cisa-kev"), health("omarchy"), health("arch"), health("aur"), health("flatpak"), health("mise")],
          "summary": { "totalUpdates": 3, "watchedUpdates": 0, "securityFindings": 0, "degradedSources": 0 },
          "items": [
            { "id": "omarchy:omarchy", "source": "omarchy", "label": "Omarchy", "installed": "1", "candidate": "2", "watchMode": "off", "watchable": true, "provenance": "live" },
            { "id": "flatpak:user:app/org.example.App/x86_64/stable", "source": "flatpak", "label": "Example App", "installed": "1", "candidate": "2", "watchMode": "off", "watchable": true, "provenance": "live" },
            { "id": "flatpak:system:app/org.example.Tool/x86_64/stable", "source": "flatpak", "label": "Example Tool", "installed": "1", "candidate": "2", "watchMode": "off", "watchable": true, "provenance": "live" }
          ],
          "findings": [],
          "notifications": []
        }
      }
    }

    function begin() {
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
        "manifest": { "id": "io.github.tomge.opatchy", "__sourceDir": sourceDir },
        "handoffTransport": fakeLauncher
      })
      if (service === null) {
        fail("Service.qml did not instantiate")
        return
      }
      var initialOperation = service.activeOperation
      check(initialOperation !== null, "initial helper snapshot did not start")
      service._controller.complete(initialOperation.id, {
        "exitCode": 0,
        "stdout": JSON.stringify(fixtureSnapshot()),
        "stderr": "",
        "timedOut": false,
        "outputTooLarge": false
      })
      check(service.lastSnapshot !== null, "fixture snapshot was not accepted")
      snapshotBeforeActions = JSON.stringify(service.lastSnapshot)
      service.operationFailed.connect(function() {
        failureTimer.restart()
      })
      startNext()
    }

    function startNext() {
      if (stage === 0) {
        check(service.openOmarchyUpdate(), "Omarchy handoff was not accepted")
        check(!service.openOmarchyUpdate(), "repeat click started a second handoff")
      }
      else if (stage === 1) check(service.openFlatpakUserUpdate(), "user Flatpak handoff was not accepted")
      else if (stage === 2) check(service.openFlatpakSystemUpdate(), "system Flatpak handoff was not accepted")
      else if (stage === 3) {
        check(launches.length === 3, "exactly three terminal handoffs were started")
        check(JSON.stringify(launches[0]) === JSON.stringify(["/usr/bin/omarchy-launch-floating-terminal-with-presentation", "/usr/bin/omarchy-update"]), "Omarchy argv changed")
        check(JSON.stringify(launches[1]) === JSON.stringify(["/usr/bin/omarchy-launch-floating-terminal-with-presentation", "/usr/bin/flatpak", "--user", "update"]), "user Flatpak argv changed")
        check(JSON.stringify(launches[2]) === JSON.stringify(["/usr/bin/omarchy-launch-floating-terminal-with-presentation", "/usr/bin/flatpak", "--system", "update"]), "system Flatpak argv changed")
        check(service.handoffAt > 0, "successful start did not record handoffAt")
        successfulHandoffAt = service.handoffAt
        failNext = true
        check(service.openOmarchyUpdate(), "failure fixture was not accepted")
      }
    }

    QtObject {
      id: fakeLauncher

      property bool running: false
      property var capabilities: ({ "launcher": true, "omarchyUpdate": true, "flatpak": true })
      signal started()
      signal failed(string message)

      function start(actionName) {
        if (running) return false
        var argv = []
        if (actionName === "omarchy") {
          argv = ["/usr/bin/omarchy-launch-floating-terminal-with-presentation", "/usr/bin/omarchy-update"]
        } else if (actionName === "flatpak-user") {
          argv = ["/usr/bin/omarchy-launch-floating-terminal-with-presentation", "/usr/bin/flatpak", "--user", "update"]
        } else if (actionName === "flatpak-system") {
          argv = ["/usr/bin/omarchy-launch-floating-terminal-with-presentation", "/usr/bin/flatpak", "--system", "update"]
        } else {
          return false
        }
        running = true
        root.launches.push(argv)
        if (root.failNext) {
          root.failNext = false
          Qt.callLater(function() {
            fakeLauncher.running = false
            fakeLauncher.failed("fixture launcher failure")
          })
          return true
        }
        fakeProcess.running = true
        return true
      }

      property Process fakeProcess: Process {
        command: ["/usr/bin/true"]
        onStarted: {
          fakeLauncher.running = false
          fakeLauncher.started()
        }
        onExited: function(exitCode) {
          if (exitCode !== 0 && fakeLauncher.running) {
            fakeLauncher.running = false
            fakeLauncher.failed("fixture process failed")
          }
        }
      }
    }

    Connections {
      target: fakeLauncher
      function onStarted() {
        if (root.stage < 3) {
          root.stage += 1
          Qt.callLater(root.startNext)
        }
      }
    }

    Timer {
      id: failureTimer
      interval: 50
      repeat: false
      onTriggered: {
        root.check(root.service.handoffAt === root.successfulHandoffAt, "failed launch recorded a handoff")
        root.check(root.launches.length === 4, "failure fixture did not attempt exactly one launch")
        root.check(root.service.lastError.indexOf("Open update terminal") !== -1, "launcher failure was not visible")
        root.check(JSON.stringify(root.service.lastSnapshot) === root.snapshotBeforeActions, "action attempt changed the snapshot")
        console.log("action-handoff-smoke: fake launcher recorded fixed argv and start-only handoffs")
        root.service.destroy()
        Qt.exit(0)
      }
    }

    Component.onCompleted: Qt.callLater(begin)

    Timer {
      interval: 3000
      running: true
      repeat: false
      onTriggered: root.fail("handoff fixture timed out")
    }
  }
}
