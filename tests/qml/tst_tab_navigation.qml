import QtQuick 2.15
import QtTest 1.3
import qs.Ui
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

      Button {
        id: target
        activeFocusOnTab: true
        KeyNavigation.tab: nextTarget
        onClicked: route.childActivations += 1
      }

      Button {
        id: nextTarget
        x: target.width + 1
        activeFocusOnTab: true
      }

      PanelTabState {
        id: tabState
      }
    }
  }

  function test_global_shortcuts_keep_ctrl_tab_compatibility_without_consuming_vertical_navigation() {
    const state = stateComponent.createObject(root)

    compare(state.selectedTab, "Security")
    verify(state.handleKey(Qt.Key_Tab, Qt.ControlModifier))
    compare(state.selectedTab, "Omarchy")
    verify(state.handleKey(Qt.Key_Backtab, Qt.ControlModifier | Qt.ShiftModifier))
    compare(state.selectedTab, "Security")
    compare(state.handleKey(Qt.Key_Left, Qt.NoModifier), false)
    compare(state.handleKey(Qt.Key_Right, Qt.NoModifier), false)
    compare(state.handleKey(Qt.Key_Up, Qt.NoModifier), false)
    compare(state.handleKey(Qt.Key_Down, Qt.NoModifier), false)
    compare(state.selectedTab, "Security")
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

  function test_focused_host_button_receives_return_enter_and_space_before_global_navigation() {
    const route = focusRouteComponent.createObject(root)
    route.target.forceActiveFocus()
    verify(route.target.activeFocus)

    keyClick(Qt.Key_Return)
    compare(route.childActivations, 1)
    compare(route.globalNavigationEvents, 0)
    route.target.forceActiveFocus()
    keyClick(Qt.Key_Enter)
    compare(route.childActivations, 2)
    compare(route.globalNavigationEvents, 0)
    route.target.forceActiveFocus()
    keyClick(Qt.Key_Space)
    compare(route.childActivations, 3)
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
