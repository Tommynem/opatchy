import QtQuick 2.15
import QtTest 1.3
import "../../qml/components"

TestCase {
  id: root
  name: "OpatchySecurityView"
  when: true

  Component {
    id: viewComponent
    SecurityViewPresentation { }
  }

  Component {
    id: findingComponent
    SecurityFindingPresentation { }
  }

  Component {
    id: clockComponent
    SecurityClock { refreshInterval: 10 }
  }

  function source(name, status, provenance) {
    return {
      source: name,
      status: status || "ok",
      provenance: provenance || "live",
      observedAt: "2026-08-26T00:00:00.000Z",
      freshUntil: "2026-08-26T01:00:00.000Z",
      cause: null
    }
  }

  function finding(id) {
    return {
      id: id,
      itemId: "arch:openssl",
      advisoryId: id,
      cveIds: ["CVE-2026-1000"],
      severity: "high",
      fixedVersion: "3.1.2",
      installedVersion: "3.1.1",
      knownExploited: false,
      kevStatus: "not_listed",
      kevProvenance: "live",
      provenance: "live",
      status: "Fixed",
      type: "security"
    }
  }

  function snapshot(groups, securityStatus, securityProvenance) {
    return {
      payload: {
        sources: [source("security", securityStatus, securityProvenance), source("cisa-kev")],
        findings: groups || []
      }
    }
  }

  function test_presentation_exposes_clean_finding_last_known_and_unknown_states() {
    const currentTime = Date.parse("2026-08-26T00:02:00.000Z")
    const presentation = viewComponent.createObject(root, { currentTime: currentTime })

    presentation.snapshot = snapshot([])
    compare(presentation.view.kind, "clean")
    compare(presentation.view.statusText, "No known matching advisories in the current Arch data")
    presentation.snapshot = snapshot([{ itemId: "arch:openssl", findings: [finding("AVG-1")] }])
    compare(presentation.view.kind, "findings")
    compare(presentation.view.groups[0].watchTarget, "arch:openssl")
    presentation.snapshot = snapshot([], "stale", "last_good")
    compare(presentation.view.kind, "last_known")
    presentation.snapshot = snapshot([], "offline", "live")
    compare(presentation.view.kind, "unknown")
    presentation.destroy()
  }

  function test_finding_presentation_bounds_hostile_text_without_interpreting_it() {
    const hostile = "$(touch /tmp/opatchy-injection-sentinel)\n\u202e\u4f60\u597d" + String.fromCharCode(0) + "x".repeat(2000)
    const presentation = findingComponent.createObject(root, {
      group: { packageName: hostile },
      finding: {
        versionText: hostile,
        status: hostile,
        type: hostile,
        provenance: hostile,
        kevProvenance: hostile,
        ageText: hostile,
        sourceCoverageText: hostile,
        kevText: hostile
      }
    })

    verify(presentation.packageName.indexOf("\n") === -1)
    verify(presentation.versionText.indexOf(String.fromCharCode(0)) === -1)
    verify(presentation.statusText.length <= 530)
    verify(presentation.coverageText.indexOf("opatchy-injection-sentinel") !== -1)
    presentation.destroy()
  }

  function test_security_clock_updates_only_while_active() {
    const clock = clockComponent.createObject(root)

    compare(clock.interval, 10)
    clock._clockTime = 1
    compare(clock.currentTime, 1)
    clock.active = true
    verify(clock.currentTime > 1)
    const activationTime = clock.currentTime
    tryVerify(function() { return clock.currentTime > activationTime }, 100)
    const periodicTime = clock.currentTime
    clock.active = false
    wait(30)
    compare(clock.currentTime, periodicTime)
    clock.destroy()
  }
}
