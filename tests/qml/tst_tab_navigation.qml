import QtQuick 2.15
import QtTest 1.3
import "../../qml/components"

TestCase {
  id: root
  name: "OpatchyTabNavigation"
  when: true

  Component {
    id: stateComponent

    PanelTabState { }
  }

  function test_keyboard_cycles_in_the_approved_order_and_wraps() {
    const state = stateComponent.createObject(root)

    compare(state.selectedTab, "Security")
    verify(state.handleKey(Qt.Key_Tab, Qt.ControlModifier))
    compare(state.selectedTab, "Omarchy")
    verify(state.handleKey(Qt.Key_Backtab, Qt.ControlModifier | Qt.ShiftModifier))
    compare(state.selectedTab, "Security")
    verify(state.handleKey(Qt.Key_Left, Qt.NoModifier))
    compare(state.selectedTab, "mise")
    verify(state.handleKey(Qt.Key_Up, Qt.NoModifier))
    compare(state.selectedTab, "Flatpak")
    compare(state.handleKey(Qt.Key_Tab, Qt.NoModifier), false)
    state.destroy()
  }

  function test_enter_activates_and_escape_closes() {
    const state = stateComponent.createObject(root)
    var activations = 0
    var closes = 0
    state.activationRequested.connect(function() { activations += 1 })
    state.closeRequested.connect(function() { closes += 1 })

    verify(state.handleKey(Qt.Key_Return, Qt.NoModifier))
    verify(state.handleKey(Qt.Key_Escape, Qt.NoModifier))
    compare(activations, 1)
    compare(closes, 1)
    state.destroy()
  }

  function test_restore_prefers_security_for_invalid_selection_and_preserves_valid_selection() {
    const state = stateComponent.createObject(root)

    state.restore("Flatpak", false)
    compare(state.selectedTab, "Flatpak")
    state.restore("future-tab", true)
    compare(state.selectedTab, "Security")
    state.destroy()
  }
}
