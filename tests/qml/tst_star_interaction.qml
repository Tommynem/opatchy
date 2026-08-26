import QtQuick 2.15
import QtQuick.Controls 2.15 as Controls
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
    id: buttonComponent
    Window {
      id: window
      visible: true
      width: 120
      height: 48
      property int activations: 0
      Controls.Button {
        id: button
        width: 120
        height: 48
        text: "Watch"
        activeFocusOnTab: true
        onClicked: window.activations += 1
      }
      property alias button: button
    }
  }

  Component {
    id: keyboardComponent
    FocusScope {
      id: route
      focus: true
      property int activations: 0
      Controls.Button {
        id: button
        activeFocusOnTab: true
        onClicked: route.activations += 1
      }
      property alias button: button
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

  function test_reduced_motion_is_one_shared_star_state_preference() {
    const state = stateComponent.createObject(root)
    compare(state.reducedMotion, false)
    state.reducedMotion = true
    compare(state.reducedMotion, true)
    state.destroy()
  }

  function test_native_button_routes_pointer_space_and_enter() {
    const keyboard = keyboardComponent.createObject(root)
    keyboard.button.forceActiveFocus()
    keyClick(Qt.Key_Space)
    compare(keyboard.activations, 1)
    keyboard.button.forceActiveFocus()
    keyClick(Qt.Key_Return)
    compare(keyboard.activations, 2)
    keyboard.destroy()
    const view = buttonComponent.createObject(root)
    mouseClick(view.button)
    compare(view.activations, 1)
    view.destroy()
  }
}
