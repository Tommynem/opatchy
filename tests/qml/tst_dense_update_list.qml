import QtQuick 2.15
import QtQuick.Window 2.15
import QtTest 1.3
import qs.Commons
import "../../qml/components"

TestCase {
  id: root
  name: "OpatchyDenseUpdateList"
  when: true

  Component {
    id: listComponent

    Window {
      id: window
      visible: true
      width: 320
      height: 240
      property var requests: []
      property alias list: list
      property alias stars: stars
      property alias nextControl: nextControl

      FocusScope {
        id: nextControl
        objectName: "dense-list-next-control"
        activeFocusOnTab: true
        width: 1
        height: 1
      }

      QtObject {
        id: service
        function setStar(request) {
          window.requests.push(request)
          return true
        }
      }

      StarInteractionState {
        id: stars
        service: service
      }

      UpdateListView {
        id: list
        width: window.width
        viewportHeight: Style.space(128)
        starState: stars
        nextFocusItem: nextControl
      }
    }
  }

  function row(index, watchable) {
    const hostile = index === 0 ? "package-with-a-hostile-and-deliberately-long-identity-that-must-remain-recoverable-at-narrow-width" : "package-" + index
    return {
      target: "arch:item-" + index,
      id: "arch:item-" + index,
      identity: "arch:item-" + index,
      label: hostile,
      source: "arch",
      installed: "2026.08." + index,
      candidate: "2026.09." + index,
      watchText: watchable ? "Watch: off" : "Watch: unavailable",
      watchMode: "off",
      watchable: watchable,
      temporaryArmed: false,
      healthText: "Evidence: Current"
    }
  }

  function rows(count) {
    const values = []
    for (let index = 0; index < count; index += 1) values.push(row(index, index !== 1))
    return values
  }

  function within(item, container, description) {
    const origin = item.mapToItem(container, 0, 0)
    verify(origin.x >= 0 && origin.y >= 0, description + " starts inside the viewport")
    verify(origin.x + item.width <= container.width, description + " stays within viewport width")
    verify(origin.y + item.height <= container.height, description + " stays within viewport height")
  }

  function createList(width, count) {
    const view = listComponent.createObject(root, { width: width })
    view.list.rows = rows(count)
    tryVerify(function() { return count === 0 || view.list.listControl.count === count }, 1000)
    tryVerify(function() { return view.list.width === width }, 1000)
    return view
  }

  function test_dense_cardinality_stays_inside_one_bounded_viewport() {
    for (const width of [320, Style.space(520)]) {
      for (const count of [0, 1, 20, 100, 150]) {
        const view = createList(width, count)
        compare(view.list.width, width)
        verify(view.list.height <= view.height, "the list must not enlarge its host at " + count + " rows")
        if (count === 0) {
          verify(view.list.height > 0, "the empty evidence state remains visible")
        } else {
          compare(view.list.listControl.height, Style.space(128))
          verify(view.list.verticalScrollBar.visible, "the persistent scrollbar communicates list extent")
          verify(view.list.rowAt(0) !== null, "the first real production delegate renders")
          verify(view.list.rowAt(0).packageLabel.paintedWidth <= view.list.rowAt(0).packageLabel.width, "hostile package identity stays bounded")
          if (count >= 20) {
            verify(view.list.listControl.contentHeight > view.list.listControl.height, "dense evidence scrolls inside the bounded list")
            verify(view.list.visibleDelegateCount < count, "the ListView does not eagerly materialize every dense row")
          }
        }
        view.destroy()
      }
    }
  }

  function test_keyboard_navigation_and_top_control_cover_a_150_row_list() {
    const view = createList(Style.space(520), 150)
    view.requestActivate()
    tryVerify(function() { return view.active }, 1000)
    view.list.listControl.forceActiveFocus()
    tryVerify(function() { return view.list.listControl.activeFocus }, 1000)

    keyClick(Qt.Key_PageDown)
    verify(view.list.currentIndex > 0, "PageDown advances by a practical viewport step")
    keyClick(Qt.Key_PageUp)
    compare(view.list.currentIndex, 0)
    keyClick(Qt.Key_End)
    tryVerify(function() { return view.list.currentIndex === 149 && view.list.rowAt(149) !== null }, 1000)
    within(view.list.rowAt(149), view.list.listControl, "the final row after End")
    keyClick(Qt.Key_Home)
    tryVerify(function() { return view.list.currentIndex === 0 }, 1000)
    compare(Math.round(view.list.listControl.contentY), 0)
    keyClick(Qt.Key_Backtab, Qt.ShiftModifier)
    verify(!view.list.topControl.activeFocus, "Backtab bypasses a disabled Top control")

    view.list.listControl.contentY = view.list.listControl.contentHeight - view.list.listControl.height
    tryVerify(function() { return view.list.firstVisibleIndex > 0 }, 1000)
    compare(view.list.positionCue.text, view.list.rows.length + " updates | " + (view.list.firstVisibleIndex + 1) + " of " + view.list.rows.length)

    view.list.moveToIndex(149)
    tryVerify(function() { return view.list.verticalScrollBar.position > 0 }, 1000)
    view.list.listControl.forceActiveFocus()
    keyClick(Qt.Key_Backtab, Qt.ShiftModifier)
    tryVerify(function() { return view.list.topControl.activeFocus }, 1000)
    keyClick(Qt.Key_Tab)
    tryVerify(function() { return view.list.listControl.activeFocus }, 1000)
    mouseClick(view.list.topControl)
    tryVerify(function() { return view.list.currentIndex === 0 && Math.round(view.list.listControl.contentY) === 0 }, 1000)
    view.destroy()
  }

  function test_expanded_last_row_stays_visible_and_watch_modes_are_keyboard_reachable() {
    const view = createList(320, 150)
    view.requestActivate()
    tryVerify(function() { return view.active }, 1000)
    view.list.listControl.forceActiveFocus()
    tryVerify(function() { return view.list.listControl.activeFocus }, 1000)
    keyClick(Qt.Key_End)
    compare(view.list.currentIndex, 149)
    keyClick(Qt.Key_Return)
    compare(view.list.expandedIndex, 149)
    tryVerify(function() { return view.list.rowAt(149) !== null && view.list.rowAt(149).expanded }, 1000)
    verify(view.list.rowAt(149).height > Style.space(36), "expanded details increase only the selected row height")
    within(view.list.rowAt(149), view.list.listControl, "the expanded final row")

    keyClick(Qt.Key_Home)
    keyClick(Qt.Key_Return)
    tryVerify(function() { return view.list.rowAt(0).watchSelector.visible }, 1000)
    view.list.listControl.forceActiveFocus()
    keyClick(Qt.Key_Tab)
    tryVerify(function() { return view.list.rowAt(0).watchSelector.activeFocus }, 1000)
    keyClick(Qt.Key_Right)
    keyClick(Qt.Key_Return)
    compare(view.requests.length, 1)
    compare(view.requests[0].itemId, "arch:item-0")
    compare(view.requests[0].mode, "temporary")

    keyClick(Qt.Key_Backtab, Qt.ShiftModifier)
    tryVerify(function() { return view.list.listControl.activeFocus }, 1000)

    view.list.moveToIndex(1)
    keyClick(Qt.Key_Return)
    tryVerify(function() { return view.list.rowAt(1).expanded }, 1000)
    verify(!view.list.rowAt(1).watchTrigger.visible, "non-watchable rows do not expose a failing watch control")
    verify(!view.list.rowAt(1).watchSelector.visible, "non-watchable rows do not expose a hidden selector focus target")
    view.list.listControl.forceActiveFocus()
    keyClick(Qt.Key_Tab)
    tryVerify(function() { return view.nextControl.activeFocus }, 1000)
    view.destroy()
  }

  function test_target_scoped_failure_is_bounded_in_the_row_and_preserves_list_navigation() {
    const view = createList(320, 20)
    view.requestActivate()
    tryVerify(function() { return view.active }, 1000)
    view.list.listControl.forceActiveFocus()
    tryVerify(function() { return view.list.listControl.activeFocus }, 1000)
    keyClick(Qt.Key_Return)
    tryVerify(function() { return view.list.rowAt(0).watchSelector.visible }, 1000)
    keyClick(Qt.Key_Tab)
    tryVerify(function() { return view.list.rowAt(0).watchSelector.activeFocus }, 1000)
    keyClick(Qt.Key_Right)
    keyClick(Qt.Key_Return)
    compare(view.requests.length, 1)

    const row = view.list.rowAt(0)
    view.stars.acceptFailure({ kind: "set-star", itemId: "arch:item-0", mode: "temporary" }, "STATE_UNAVAILABLE: " + "x".repeat(512))
    compare(view.stars.errorTarget, "arch:item-0")
    verify(view.stars.errorText !== "")
    verify(row.failureText !== "")
    tryVerify(function() { return row.failureFeedback.visible && row.failureFeedback.text !== "" }, 1000)
    verify(row.failureFeedback.text.length <= 256, "failure feedback must be bounded before rendering")
    verify(row.failureFeedback.width <= row.width, "failure feedback must stay within the row width")
    const failureOrigin = row.failureFeedback.mapToItem(row, 0, 0)
    verify(failureOrigin.y >= 0 && failureOrigin.y + row.failureFeedback.height <= row.height, "row height must contain visible failure feedback")
    verify(row.failureFeedback.width > row.watchTrigger.width, "failure feedback must not be constrained to the compact watch button")

    keyClick(Qt.Key_Backtab, Qt.ShiftModifier)
    tryVerify(function() { return view.list.listControl.activeFocus }, 1000)
    keyClick(Qt.Key_Down)
    tryCompare(view.list, "currentIndex", 1, 1000)
    view.destroy()
  }

  function test_selector_wraps_without_overflow_at_a_narrow_component_width() {
    const view = createList(160, 1)
    view.list.activateRow(0)
    tryVerify(function() { return view.list.rowAt(0) !== null && view.list.rowAt(0).watchSelector.visible }, 1000)
    const selector = view.list.rowAt(0).watchSelector
    for (let index = 0; index < 3; index += 1) {
      const control = selector.buttonAt(index)
      const origin = control.mapToItem(selector, 0, 0)
      verify(origin.x >= 0 && origin.x + control.width <= selector.width, "watch selector controls remain horizontally bounded")
      verify(control.contentItem.width <= control.availableWidth, "watch selector labels fit their rendered control")
    }
    view.destroy()
  }
}
