import QtQuick
import "../models/TabModel.js" as TabModel

QtObject {
  id: root

  property string selectedTab: "Security"
  signal selectionRequested(string tab)
  signal activationRequested()
  signal closeRequested()

  function restore(storedTab, urgentSecurity) {
    selectedTab = TabModel.restoreSelection(storedTab, urgentSecurity)
  }

  function select(tab, persist) {
    var selected = TabModel.restoreSelection(tab, false)
    if (selectedTab === selected) return
    selectedTab = selected
    if (persist) selectionRequested(selected)
  }

  function move(direction) { cycleTab(direction) }

  function cycleTab(direction) {
    selectedTab = TabModel.nextTab(selectedTab, direction)
    selectionRequested(selectedTab)
  }

  function handleKey(key, modifiers) {
    var reverse = key === Qt.Key_Backtab || (modifiers & Qt.ShiftModifier)
    if ((key === Qt.Key_Tab || key === Qt.Key_Backtab) && (modifiers & Qt.ControlModifier)) {
      cycleTab(reverse ? -1 : 1)
      return true
    }
    if (key === Qt.Key_Left || key === Qt.Key_Up) {
      cycleTab(-1)
      return true
    }
    if (key === Qt.Key_Right || key === Qt.Key_Down) {
      cycleTab(1)
      return true
    }
    if (key === Qt.Key_Escape) {
      closeRequested()
      return true
    }
    if (key === Qt.Key_Return || key === Qt.Key_Enter) {
      activationRequested()
      return true
    }
    return false
  }
}
