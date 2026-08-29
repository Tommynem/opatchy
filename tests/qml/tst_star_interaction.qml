import QtQuick 2.15
import QtQuick.Window 2.15
import QtTest 1.3
import "../../qml/components"

TestCase {
  id: root
  name: "OpatchyStarInteraction"
  when: true

  Component {
    id: stateComponent
    StarInteractionState { }
  }

  Component {
    id: consumerComponent
    StarFeedbackConsumer { }
  }

  Component {
    id: starButtonComponent
    Window {
      id: window
      visible: true
      width: 120
      height: 48
      property var service: ({ requests: [], setStar: function(request) { this.requests.push(request); return true } })
      StarInteractionState { id: stars; service: window.service }
      StarButton {
        id: button
        width: 120
        height: 48
        starState: stars
        target: "arch:demo"
        confirmedMode: "off"
        watchable: true
      }
      property alias button: button
      property alias stars: stars
    }
  }

  Component {
    id: securityFindingComponent
    Window {
      id: window
      visible: true
      width: 160
      height: 120
      property var service: ({ requests: [], setStar: function(request) { this.requests.push(request); return true } })
      StarInteractionState { id: stars; service: window.service }
      SecurityFindingRow {
        id: row
        width: parent.width
        group: ({ watchTarget: "arch:demo", watchMode: "off", watchable: true })
        confirmedMode: "off"
        watchable: true
        finding: ({
          advisoryId: "AVG-1",
          cveIds: ["CVE-2026-1001", "CVE-2026-1000"],
          versionText: "Installed 1.0; fixed in 2.0",
          status: "Fixed",
          type: "security",
          provenance: "live",
          kevProvenance: "live",
          ageText: "now",
          sourceCoverageText: "current",
          kevText: "not listed",
          watchRequest: ({ itemId: "arch:demo", securityAdvisory: "AVG-1", fixedVersion: "2.0", cveIds: ["CVE-2026-1001", "CVE-2026-1000"] })
        })
        starState: stars
      }
      property alias row: row
      property alias stars: stars
    }
  }

  function test_pending_request_retains_confirmed_mode_and_coalesces_rapid_clicks() {
    const state = stateComponent.createObject(root)
    const service = { requests: [], setStar: function(request) { this.requests.push(request); return true } }
    state.service = service

    compare(state.request("arch:demo", "off", true), true)
    compare(state.modeFor("arch:demo", "off"), "off")
    compare(state.request("arch:demo", "off", true), false)
    compare(service.requests.length, 1)
    compare(service.requests[0].mode, "temporary")
    state.acceptResult({ payload: { itemId: "arch:other", mode: "temporary" } })
    compare(state.pending, true)
    state.acceptResult({ payload: { itemId: "arch:demo", mode: "temporary" } }, { id: 99, kind: "set-star", itemId: "arch:other", mode: "temporary" })
    compare(state.pending, true)
    state.acceptResult({ payload: { itemId: "arch:demo", mode: "temporary" } }, { id: 1, kind: "set-star", itemId: "arch:demo", mode: "temporary" })
    compare(state.pending, false)
    compare(state.modeFor("arch:demo", "off"), "temporary")
    state.destroy()
  }

  function test_explicit_watch_mode_requests_respect_the_authoritative_current_mode() {
    const state = stateComponent.createObject(root)
    const service = { requests: [], setStar: function(request) { this.requests.push(request); return true } }
    state.service = service
    state.snapshotGeneration = "generation-1"

    verify(state.requestMode("arch:demo", "off", true, "permanent"))
    compare(service.requests[0].mode, "permanent")
    state.acceptResult({ payload: { itemId: "arch:demo", mode: "permanent", watchArmed: false } }, { kind: "set-star", itemId: "arch:demo", mode: "permanent" })
    compare(state.modeFor("arch:demo", "off"), "permanent")
    verify(!state.requestMode("arch:demo", "off", true, "permanent"), "the visible selected mode is not redundantly sent")
    verify(state.requestMode("arch:demo", "off", true, "off"))
    compare(service.requests[1].mode, "off")
    state.destroy()
  }

  function test_failed_other_operation_does_not_label_or_roll_back_the_pending_target() {
    const state = stateComponent.createObject(root)
    state.service = { setStar: function() { return true } }
    verify(state.request("arch:demo", "temporary", true))
    state.acceptFailure({ kind: "set-star", itemId: "arch:other", mode: "permanent" }, "other failed")
    compare(state.pending, true)
    compare(state.errorText, "")
    state.acceptFailure({ kind: "set-star", itemId: "arch:demo", mode: "permanent" }, "watch failed")
    compare(state.pending, false)
    compare(state.modeFor("arch:demo", "temporary"), "temporary")
    compare(state.errorText, "watch failed")
    state.destroy()
  }

  function test_new_validated_generation_reconciles_a_temporary_override() {
    const state = stateComponent.createObject(root)
    state.service = { setStar: function() { return true } }
    state.snapshotGeneration = "generation-1"
    verify(state.request("arch:demo", "off", true))
    state.acceptResult({ payload: { itemId: "arch:demo", mode: "temporary", watchArmed: true } }, { kind: "set-star", itemId: "arch:demo", mode: "temporary" })
    compare(state.modeFor("arch:demo", "off"), "temporary")
    state.snapshotGeneration = "generation-2"
    compare(state.modeFor("arch:demo", "off"), "off")
    state.destroy()
  }

  function test_second_request_uses_the_authoritative_temporary_override() {
    const state = stateComponent.createObject(root)
    const service = { requests: [], setStar: function(request) { this.requests.push(request); return true } }
    state.service = service
    verify(state.request("arch:demo", "off", true))
    state.acceptResult({ payload: { itemId: "arch:demo", mode: "temporary", watchArmed: true } }, { kind: "set-star", itemId: "arch:demo", mode: "temporary" })

    verify(state.request("arch:demo", "off", true))

    compare(service.requests.length, 2)
    compare(service.requests[1].mode, "permanent")
    state.destroy()
  }

  function test_reduced_motion_controls_the_shared_feedback_duration() {
    const state = stateComponent.createObject(root)
    compare(state.feedbackDuration, 100)
    state.reducedMotion = true
    compare(state.feedbackDuration, 0)
    state.destroy()
  }

  function test_shared_consumers_receive_target_scoped_confirmed_feedback() {
    const state = stateComponent.createObject(root)
    const first = consumerComponent.createObject(root, { starState: state, target: "arch:demo" })
    const second = consumerComponent.createObject(root, { starState: state, target: "arch:demo" })
    const other = consumerComponent.createObject(root, { starState: state, target: "arch:other" })
    first.confirmedMode = "temporary"
    second.confirmedMode = "temporary"
    compare(first.activations, 1)
    compare(second.activations, 1)
    compare(other.activations, 0)
    first.temporaryArmed = true
    second.temporaryArmed = true
    compare(first.activations, 2)
    compare(second.activations, 2)
    compare(other.activations, 0)
    first.destroy()
    second.destroy()
    other.destroy()
    state.destroy()
  }

  function test_native_button_routes_pointer_space_and_enter() {
    const view = starButtonComponent.createObject(root)
    mouseClick(view.button)
    compare(view.service.requests.length, 1)
    compare(view.service.requests[0].mode, "temporary")
    compare(view.button.confirmedMode, "off")
    view.button.forceActiveFocus()
    keyClick(Qt.Key_Space)
    view.button.forceActiveFocus()
    keyClick(Qt.Key_Return)
    compare(view.service.requests.length, 1)
    view.destroy()
  }

  function test_security_fixed_version_action_routes_native_keyboard_request_with_exact_evidence() {
    const view = securityFindingComponent.createObject(root)
    verify(view.row.fixedVersionWatch.visible)
    verify(view.row.fixedVersionWatch.width <= view.width)
    view.requestActivate()
    tryVerify(function() { return view.active })
    view.row.fixedVersionWatch.forceActiveFocus()
    tryVerify(function() { return view.row.fixedVersionWatch.activeFocus })
    keyClick(Qt.Key_Space)
    compare(view.service.requests.length, 1)
    compare(view.service.requests[0].itemId, "arch:demo")
    compare(view.service.requests[0].mode, "temporary")
    compare(view.service.requests[0].securityAdvisory, "AVG-1")
    compare(view.service.requests[0].fixedVersion, "2.0")
    compare(view.service.requests[0].cveIds.join(","), "CVE-2026-1001,CVE-2026-1000")
    view.destroy()
  }

  function test_security_fixed_version_action_stops_being_actionable_while_pending_and_after_success() {
    const view = securityFindingComponent.createObject(root)
    view.stars.snapshotGeneration = "generation-1"
    view.requestActivate()
    tryVerify(function() { return view.active })
    view.row.fixedVersionWatch.forceActiveFocus()
    keyClick(Qt.Key_Space)
    compare(view.service.requests.length, 1)
    compare(view.stars.pending, true)
    tryVerify(function() { return !view.row.fixedVersionWatch.visible })
    verify(view.row.watchUnavailable.visible)
    verify(view.row.watchUnavailable.text.indexOf("pending") !== -1)

    view.stars.acceptResult({ payload: { itemId: "arch:demo", mode: "temporary", watchArmed: true } }, {
      kind: "set-star", itemId: "arch:demo", mode: "temporary", securityAdvisory: "AVG-1", fixedVersion: "2.0", cveIds: ["CVE-2026-1001", "CVE-2026-1000"]
    })
    compare(view.stars.pending, false)
    tryVerify(function() { return !view.row.fixedVersionWatch.visible })
    verify(view.row.watchUnavailable.text.indexOf("temporary watch") !== -1)

    view.row.confirmedMode = "temporary"
    view.stars.snapshotGeneration = "generation-2"
    tryVerify(function() { return !view.row.fixedVersionWatch.visible })
    verify(view.row.watchUnavailable.text.indexOf("temporary watch") !== -1)
    view.destroy()
  }

  function test_security_fixed_version_action_names_unavailable_evidence_without_a_disabled_control() {
    const view = securityFindingComponent.createObject(root)
    view.row.finding = Object.assign({}, view.row.finding, { watchRequest: null })
    tryVerify(function() { return !view.row.fixedVersionWatch.visible })
    verify(view.row.watchUnavailable.visible)
    verify(view.row.watchUnavailable.text.indexOf("unavailable") !== -1)
    verify(view.row.watchUnavailable.width <= view.width)
    view.destroy()
  }

  function test_security_condition_result_correlation_requires_the_exact_request_identity() {
    const state = stateComponent.createObject(root)
    const service = { requests: [], setStar: function(request) { this.requests.push(request); return true } }
    const condition = { itemId: "arch:demo", securityAdvisory: "AVG-1", fixedVersion: "2.0", cveIds: ["CVE-2026-1001", "CVE-2026-1000"] }
    state.service = service

    verify(state.requestSecurityCondition(condition, "off", true))
    state.acceptResult({ payload: { itemId: "arch:demo", mode: "temporary", watchArmed: true } }, {
      kind: "set-star", itemId: "arch:demo", mode: "temporary", securityAdvisory: "AVG-1", fixedVersion: "2.0", cveIds: ["CVE-2026-1000", "CVE-2026-1001"]
    })
    compare(state.pending, true)
    state.acceptResult({ payload: { itemId: "arch:demo", mode: "temporary", watchArmed: true } }, {
      kind: "set-star", itemId: "arch:demo", mode: "temporary", securityAdvisory: "AVG-1", fixedVersion: "2.0", cveIds: ["CVE-2026-1001", "CVE-2026-1000"]
    })
    compare(state.pending, false)
    state.destroy()
  }
}
