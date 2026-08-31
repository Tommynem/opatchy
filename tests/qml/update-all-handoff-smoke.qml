import QtQuick
import Quickshell

ShellRoot {
  Item {
    id: root

    property string sourceDir: Quickshell.env("OPATCHY_TEST_ROOT")
    property var service: null
    property var launches: []
    property int scenario: 0
    property int exitStatus: -1

    function fail(message) {
      console.error("update-all-handoff-smoke: " + message)
      finish(1)
    }

    function check(condition, message) {
      if (condition) return true
      fail(message)
      return false
    }

    function finish(status) {
      if (exitStatus !== -1) return
      exitStatus = status
      if (service) service.destroy()
      Qt.exit(status)
    }

    function health(name) {
      var value = { source: name, status: "ok", provenance: "live", observedAt: "2026-08-26T00:00:00.000Z", freshUntil: "2026-08-26T00:05:00.000Z", cause: null }
      if (name === "flatpak") value.scopes = ["user", "system"].map(function(scope) {
        return { scope: scope, status: "ok", provenance: "live", observedAt: "2026-08-26T00:00:00.000Z", freshUntil: "2026-08-26T00:05:00.000Z", cause: null }
      })
      return value
    }

    function snapshot() {
      return {
        protocolVersion: 1,
        kind: "snapshot",
        generatedAt: "2026-08-26T00:00:00.000Z",
        generationId: "update-all-fixture",
        payload: {
          scanState: "complete",
          sources: ["security", "cisa-kev", "omarchy", "arch", "aur", "flatpak", "mise"].map(health),
          summary: { totalUpdates: 3, watchedUpdates: 0, securityFindings: 0, degradedSources: 0 },
          items: [
            { id: "omarchy:fixture", source: "omarchy", label: "fixture", installed: "1", candidate: "2", installedFingerprint: "1", candidateFingerprint: "2", watchMode: "off", watchArmed: false, watchable: true, provenance: "live" },
            { id: "flatpak:user:app/example", source: "flatpak", label: "fixture", installed: "1", candidate: "2", installedFingerprint: "1", candidateFingerprint: "2", watchMode: "off", watchArmed: false, watchable: true, provenance: "live" },
            { id: "flatpak:system:app/example", source: "flatpak", label: "fixture", installed: "1", candidate: "2", installedFingerprint: "1", candidateFingerprint: "2", watchMode: "off", watchArmed: false, watchable: true, provenance: "live" }
          ],
          findings: [], notifications: []
        }
      }
    }

    function begin() {
      var component = Qt.createComponent("file://" + sourceDir + "/Service.qml")
      service = component.createObject(root, { manifest: { id: "io.github.tommynem.opatchy", __sourceDir: sourceDir }, handoffTransport: fakeLauncher })
      if (!check(service !== null, "Service.qml did not instantiate")) return
      var operation = service.activeOperation
      service._controller.complete(operation.id, { exitCode: 0, stdout: JSON.stringify(snapshot()), stderr: "", timedOut: false, outputTooLarge: false })
      if (!check(service.canUpdateAll, "completion-capable fake must enable update-all")) return
      var incompleteService = component.createObject(root, { manifest: { id: "io.github.tommynem.opatchy", __sourceDir: sourceDir }, handoffTransport: incompleteLauncher })
      if (!check(incompleteService !== null, "incomplete transport fixture did not instantiate")) return
      var incompleteOperation = incompleteService.activeOperation
      incompleteService._controller.complete(incompleteOperation.id, { exitCode: 0, stdout: JSON.stringify(snapshot()), stderr: "", timedOut: false, outputTooLarge: false })
      if (!check(!incompleteService.canUpdateAll, "transport without completion signal enabled update-all")) return
      incompleteService.destroy()
      runScenario()
    }

    function runScenario() {
      launches = []
      fakeLauncher.exitCode = root.scenario === 2 ? 1 : 0
      fakeLauncher.rejectStart = root.scenario === 3
      fakeLauncher.staleUserBeforeFinish = root.scenario === 1
      if (!check(service.requestUpdateAll(), "one update-all activation was not accepted")) return
      if (root.scenario === 3) verifyScenario()
    }

    function markFlatpakUserStale() {
      var nextState = Object.assign({}, service._state)
      var nextSnapshot = JSON.parse(JSON.stringify(nextState.lastSnapshot))
      nextSnapshot.payload.sources.filter(function(value) { return value.source === "flatpak" })[0].scopes[0].status = "stale"
      nextState.lastSnapshot = nextSnapshot
      service._state = nextState
      return !service.canOpenFlatpakUserUpdate
    }

    function verifyScenario() {
      if (scenario === 0 && JSON.stringify(launches) !== JSON.stringify(["omarchy", "flatpak-user", "flatpak-system"])) return fail("all eligible actions did not run in fixed order")
      if (scenario === 1 && JSON.stringify(launches) !== JSON.stringify(["omarchy", "flatpak-system"])) return fail("stale user action was not skipped between completions")
      if (scenario === 2 && launches.length !== 1) return fail("nonzero completion did not terminate the batch")
      if (scenario === 3 && launches.length !== 0) return fail("start rejection launched an action")
      if (!check(!service._updateAllActive, "completed or failed batch remained active")) return
      if (scenario >= 2 && !check(service.lastError.indexOf("Open update terminal") !== -1, "failed batch was not visible")) return
      if (scenario === 3) finish(0)
      else { scenario += 1; Qt.callLater(runScenario) }
    }

    QtObject {
      id: fakeLauncher
      property bool running: false
      property bool rejectStart: false
      property bool staleUserBeforeFinish: false
      property int exitCode: 0
      property var capabilities: ({ launcher: true, omarchyUpdate: true, flatpak: true })
      signal started()
      signal failed(string message)
      signal finished(int exitCode)

      function start(actionName) {
        if (running || rejectStart) return false
        running = true
        root.launches.push(actionName)
        Qt.callLater(function() {
          fakeLauncher.started()
          Qt.callLater(function() {
            if (fakeLauncher.staleUserBeforeFinish && !root.check(root.markFlatpakUserStale(), "stale scope remained eligible before completion")) return
            fakeLauncher.running = false
            fakeLauncher.finished(fakeLauncher.exitCode)
            Qt.callLater(function() {
              if (!root.service._updateAllActive) root.verifyScenario()
            })
          })
        })
        return true
      }
    }

    QtObject {
      id: incompleteLauncher
      property bool running: false
      property var capabilities: ({ launcher: true, omarchyUpdate: true, flatpak: true })
      signal started()
      signal failed(string message)

      function start(actionName) { return false }
    }

    Component.onCompleted: begin()

    Timer {
      interval: 3000
      running: true
      repeat: false
      onTriggered: root.fail("fixture timed out")
    }
  }
}
