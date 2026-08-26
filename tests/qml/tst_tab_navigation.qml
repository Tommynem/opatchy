import QtQuick 2.15
import QtQuick.Controls 2.15 as Controls
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

  Component {
    id: focusRouteComponent

    FocusScope {
      id: route
      focus: true

      property int childActivations: 0
      property int globalNavigationEvents: 0
      property alias target: target
      property alias nextTarget: nextTarget

      Keys.priority: Keys.AfterItem
      Keys.onPressed: function(event) {
        if (tabState.handleKey(event.key, event.modifiers)) {
          route.globalNavigationEvents += 1
          event.accepted = true
        }
      }

      Controls.Button {
        id: target
        activeFocusOnTab: true
        KeyNavigation.tab: nextTarget
        onClicked: route.childActivations += 1
      }

      Controls.Button {
        id: nextTarget
        x: target.width + 1
        activeFocusOnTab: true
      }

      PanelTabState {
        id: tabState
      }
    }
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

  function test_escape_closes() {
    const state = stateComponent.createObject(root)
    var closes = 0
    state.closeRequested.connect(function() { closes += 1 })

    verify(state.handleKey(Qt.Key_Escape, Qt.NoModifier))
    compare(closes, 1)
    state.destroy()
  }

  function test_enter_is_not_a_global_navigation_shortcut() {
    const state = stateComponent.createObject(root)

    compare(state.handleKey(Qt.Key_Return, Qt.NoModifier), false)
    compare(state.handleKey(Qt.Key_Enter, Qt.NoModifier), false)
    state.destroy()
  }

  function test_focused_button_receives_enter_before_global_navigation() {
    const route = focusRouteComponent.createObject(root)
    route.target.forceActiveFocus()
    verify(route.target.activeFocus)

    keyClick(Qt.Key_Return)
    compare(route.childActivations, 1)
    compare(route.globalNavigationEvents, 0)
    route.target.forceActiveFocus()
    keyClick(Qt.Key_Tab)
    compare(route.globalNavigationEvents, 0)
    route.destroy()
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
