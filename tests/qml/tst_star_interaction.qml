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
    id: sourceContentComponent

    Window {
      id: window
      visible: true
      width: 160
      height: 192
      property var snapshot: root.snapshotFor("generation-1", "off", "ok")

      QtObject {
        id: service
        property var requests: []
        signal inventoryChanged(string source, var inventory, var operation)
        signal starResultChanged(var result, var operation)
        signal starFailed(var operation, string message)

        function setStar(request) {
          requests.push(request)
          return true
        }
      }

      SourceContent {
        id: sourceContent
        width: parent.width
        tab: "System"
        service: service
        snapshot: window.snapshot
      }

      StarButton {
        id: first
        width: parent.width
        height: 48
        y: 0
        z: 1
        starState: sourceContent.starState
        target: "arch:demo"
        confirmedMode: "off"
        watchable: true
      }

      StarButton {
        id: second
        width: parent.width
        height: 48
        y: 48
        z: 1
        starState: sourceContent.starState
        target: "arch:demo"
        confirmedMode: "off"
        watchable: true
      }

      StarButton {
        id: other
        width: parent.width
        height: 48
        y: 96
        z: 1
        starState: sourceContent.starState
        target: "arch:other"
        confirmedMode: "off"
        watchable: true
      }

      property alias sourceContent: sourceContent
      property alias service: service
      property alias first: first
      property alias second: second
      property alias other: other
    }
  }

  function snapshotFor(generationId, watchMode, sourceStatus) {
    return {
      generationId: generationId,
      payload: {
        sources: [{ source: "arch", status: sourceStatus, provenance: "live" }],
        items: [{
          id: "arch:demo",
          source: "arch",
          label: "Demo",
          installed: "1.0",
          candidate: "2.0",
          watchMode: watchMode,
          watchArmed: false,
          watchable: true
        }]
      }
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

  function test_source_content_reconciles_real_same_target_buttons_and_retains_stale_watched_rows() {
    const view = sourceContentComponent.createObject(root)
    verify(view.sourceContent.starState !== null)
    compare(view.first.starState, view.sourceContent.starState)
    compare(view.second.starState, view.sourceContent.starState)
    compare(view.other.starState, view.sourceContent.starState)
    compare(view.first.view.mode, "off")
    compare(view.second.view.mode, "off")
    compare(view.other.view.mode, "off")

    verify(view.sourceContent.starState.request("arch:demo", "off", true))
    compare(view.service.requests.length, 1)
    compare(view.service.requests[0].itemId, "arch:demo")
    compare(view.service.requests[0].mode, "temporary")

    view.service.starResultChanged({ payload: { itemId: "arch:demo", mode: "temporary", watchArmed: true } }, {
      kind: "set-star", itemId: "arch:demo", mode: "temporary"
    })
    compare(view.first.view.mode, "temporary")
    compare(view.second.view.mode, "temporary")
    compare(view.other.view.mode, "off")

    view.snapshot = snapshotFor("generation-2", "off", "ok")
    compare(view.first.view.mode, "off")
    compare(view.second.view.mode, "off")
    compare(view.other.view.mode, "off")

    view.snapshot = snapshotFor("generation-3", "permanent", "stale")
    view.sourceContent.watchedOnly = true
    compare(view.sourceContent.displayedRows.length, 1)
    compare(view.sourceContent.displayedRows[0].target, "arch:demo")
    compare(view.sourceContent.displayedRows[0].healthText, "Source health: Last known")
    view.destroy()
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
}
