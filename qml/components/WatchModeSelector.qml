import QtQuick
import qs.Commons
import qs.Ui

FocusScope {
  id: root

  property var starState: null
  property string target: ""
  property string confirmedMode: "off"
  property bool watchable: false
  property Item previousFocusItem: null
  property Item nextFocusItem: null
  readonly property string effectiveMode: starState ? starState.modeFor(target, confirmedMode) : confirmedMode
  property int selectedIndex: modeIndex(effectiveMode)
  readonly property var modes: ["off", "temporary", "permanent"]

  implicitHeight: controls.implicitHeight
  height: implicitHeight
  activeFocusOnTab: watchable

  onEffectiveModeChanged: selectedIndex = modeIndex(effectiveMode)

  Keys.priority: Keys.BeforeItem
  Keys.onLeftPressed: function(event) {
    selectedIndex = Math.max(0, selectedIndex - 1)
    event.accepted = true
  }
  Keys.onRightPressed: function(event) {
    selectedIndex = Math.min(modes.length - 1, selectedIndex + 1)
    event.accepted = true
  }
  Keys.onReturnPressed: function(event) {
    applySelectedMode()
    event.accepted = true
  }
  Keys.onSpacePressed: function(event) {
    applySelectedMode()
    event.accepted = true
  }
  Keys.onTabPressed: function(event) {
    if (nextFocusItem) nextFocusItem.forceActiveFocus()
    event.accepted = nextFocusItem !== null
  }
  Keys.onBacktabPressed: function(event) {
    if (previousFocusItem) previousFocusItem.forceActiveFocus()
    event.accepted = previousFocusItem !== null
  }

  Column {
    id: controls
    width: parent.width
    spacing: Style.spacing.xs

    Text {
      text: "Watch"
      textFormat: Text.PlainText
      color: Color.foreground
      font.pixelSize: Style.font.caption
    }

    Flow {
      width: parent.width
      spacing: Style.spacing.xs

      Repeater {
        id: modeButtons
        model: root.modes

        delegate: Button {
          required property int index
          required property string modelData
          width: root.width < 200 ? parent.width : (parent.width - parent.spacing * 2) / 3
          text: modelData === "off" ? "Off" : (modelData === "temporary" ? "Temporary" : "Permanent")
          tooltipText: modeTooltip(modelData)
          foreground: Color.foreground
          fontSize: Style.font.caption
          focusable: false
          bordered: true
          selected: root.selectedIndex === index
          enabled: root.watchable && root.starState && !root.starState.pending
          onClicked: {
            root.selectedIndex = index
            root.applySelectedMode()
          }
        }
      }
    }
  }

  function applySelectedMode() {
    if (!starState || !watchable) return false
    return starState.requestMode(target, confirmedMode, watchable, modes[selectedIndex])
  }

  function modeIndex(mode) {
    var index = modes.indexOf(mode)
    return index === -1 ? 0 : index
  }

  function buttonAt(index) {
    return modeButtons.itemAt(index)
  }

  function modeTooltip(mode) {
    if (mode === "off") return "Do not watch this package"
    if (mode === "temporary") return "Watch until the next observed package change or update"
    return "Watch permanently"
  }
}
