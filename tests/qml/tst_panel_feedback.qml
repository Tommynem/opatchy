import QtQuick 2.15
import QtQuick.Window 2.15
import QtTest 1.3
import "../../qml/components"

TestCase {
  id: root
  name: "OpatchyPanelFeedback"
  when: true

  Component {
    id: tabStripComponent
    Window {
      visible: true
      width: 160
      height: 400
      property alias strip: strip

      SourceTabStrip {
        id: strip
        anchors.fill: parent
      }
    }
  }

  function tab(name, count, healthText) {
    return {
      name: name,
      count: count,
      healthText: healthText,
      glyph: healthText === "Current" ? "OK" : "!",
      tooltip: healthText
    }
  }

  function boundsWithin(item, container, description) {
    const origin = item.mapToItem(container, 0, 0)
    verify(origin.x >= 0 && origin.y >= 0, description + " must start inside its tab cell")
    verify(origin.x + item.width <= container.width, description + " must not extend past its tab cell")
    verify(origin.y + item.height <= container.height, description + " must not extend past its tab cell")
  }

  function rectanglesOverlap(first, second, container) {
    const firstOrigin = first.mapToItem(container, 0, 0)
    const secondOrigin = second.mapToItem(container, 0, 0)
    return firstOrigin.x < secondOrigin.x + second.width
      && secondOrigin.x < firstOrigin.x + first.width
      && firstOrigin.y < secondOrigin.y + second.height
      && secondOrigin.y < firstOrigin.y + first.height
  }

  function test_all_six_tabs_remain_visible_bounded_and_keyboard_operable_at_narrow_width() {
    const view = tabStripComponent.createObject(root)
    view.strip.tabs = [
      tab("Security", 2000, "Partial coverage, not applicable on this host"),
      tab("Omarchy", 1000, "Current validated source evidence"),
      tab("System", 3000, "Unavailable current source evidence"),
      tab("AUR", 0, "Not applicable on this host"),
      tab("Flatpak", 1000, "Last known source evidence retained"),
      tab("mise", 0, "Incompatible source data for this Opatchy version")
    ]

    tryVerify(function() { return view.strip.tabButtonAt(5) !== null }, 1000)
    tryVerify(function() {
      return view.strip.tabButtonAt(5).height > 0
    }, 1000)
    tryVerify(function() {
      const lastButton = view.strip.tabButtonAt(5)
      return view.strip.columnCount === 1
        && lastButton.x >= 0
        && lastButton.x + lastButton.width <= view.strip.width
        && lastButton.y + lastButton.height <= view.strip.height
    }, 1000)

    for (let index = 0; index < 6; index += 1) {
      const button = view.strip.tabButtonAt(index)
      verify(button !== null, "each tab must be a concrete Repeater delegate")
      verify(button.visible, "each tab delegate must be visible")
      verify(button.enabled, "each tab delegate must remain enabled")
      verify(button.focusable, "each tab delegate must expose native keyboard focus")
      verify(button.width > 0 && button.height > 0, "each tab delegate must have positive geometry")
      verify(button.x >= 0 && button.x + button.width <= view.strip.width, "delegate must stay within strip width")
      verify(button.y >= 0 && button.y + button.height <= view.strip.height, "delegate must stay within strip height")
      verify(button.tabIcon.visible, "each tab must visibly render its glyph")
      verify(button.tabLabel.visible, "each tab must visibly render its name and count")
      verify(button.tabHealth.visible, "each tab must visibly render its health text")
      verify(button.tabHealth.text === view.strip.tabs[index].healthText, "health text must not be tooltip-only")
      boundsWithin(button.tabIcon, button, "tab glyph")
      boundsWithin(button.tabLabel, button, "tab name/count")
      boundsWithin(button.tabHealth, button, "tab health")
      verify(button.tabIcon.paintedWidth <= button.tabIcon.width, "tab glyph paint must stay within its box")
      verify(button.tabLabel.paintedWidth <= button.tabLabel.width, "tab name/count paint must stay within its box")
      verify(button.tabHealth.paintedWidth <= button.tabHealth.width, "tab health paint must stay within its box")
    }
    compare(view.strip.columnCount, 1)
    for (let index = 0; index < 6; index += 1) {
      for (let otherIndex = index + 1; otherIndex < 6; otherIndex += 1) {
        verify(!rectanglesOverlap(view.strip.tabButtonAt(index), view.strip.tabButtonAt(otherIndex), view.strip), "tab cells must not overlap")
      }
    }

    const selected = []
    view.strip.selected.connect(function(name) { selected.push(name) })
    mouseClick(view.strip.tabButtonAt(4))
    compare(selected, ["Flatpak"])
    view.strip.selectedTab = selected[0]
    compare(view.strip.tabButtonAt(4).selected, true)
    view.strip.tabButtonAt(4).forceActiveFocus()
    tryVerify(function() { return view.strip.tabButtonAt(4).activeFocus }, 1000)
    keyClick(Qt.Key_Return)
    keyClick(Qt.Key_Space)
    compare(selected, ["Flatpak", "Flatpak", "Flatpak"])
    view.destroy()
  }
}
