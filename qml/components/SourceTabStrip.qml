import QtQuick
import qs.Commons
import qs.Ui

FocusScope {
  id: root

  property var tabs: []
  property string selectedTab: "Security"
  property Item previousFocusItem: null
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  signal selected(string tab)

  activeFocusOnTab: true
  Keys.priority: Keys.BeforeItem
  Keys.onLeftPressed: function(event) {
    root.selectRelative(-1)
    event.accepted = true
  }
  Keys.onRightPressed: function(event) {
    root.selectRelative(1)
    event.accepted = true
  }
  Keys.onPressed: function(event) {
    if (event.key === Qt.Key_Backtab && root.previousFocusItem) {
      root.previousFocusItem.forceActiveFocus()
      event.accepted = true
      return
    }
    if (event.modifiers !== Qt.NoModifier) return
    if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
      root.selected(root.selectedTab)
      event.accepted = true
    }
  }

  readonly property int tabButtonCount: tabs && typeof tabs.length === "number" ? tabs.length : 0
  readonly property real minimumTabWidth: Style.font.bodySmall * 12 + Style.spacing.md * 2
  readonly property int columnCount: width >= minimumTabWidth * 3 + Style.spacing.xs * 2 ? 3
    : (width >= minimumTabWidth * 2 + Style.spacing.xs ? 2 : 1)
  readonly property int tabRowCount: Math.ceil(tabButtonCount / columnCount)
  readonly property real tabWidth: Math.max(1, (width - Style.spacing.xs * (columnCount - 1)) / columnCount)
  readonly property bool tabsFitWidth: tabButtonCount === tabRepeater.count
    && tabWidth * columnCount + Style.spacing.xs * (columnCount - 1) <= width

  implicitHeight: tabGrid.implicitHeight

  Grid {
    id: tabGrid
    width: parent.width
    columns: root.columnCount
    columnSpacing: Style.spacing.xs
    rowSpacing: Style.spacing.xs

    Repeater {
      id: tabRepeater
      model: root.tabs

      delegate: Button {
        required property var modelData
        property alias tabIcon: tabIconItem
        property alias tabLabel: tabLabelItem
        property alias tabHealth: tabHealthItem

        width: root.tabWidth
        implicitHeight: tabContent.implicitHeight + Style.spacing.xs * 2
        height: implicitHeight
        text: ""
        iconText: ""
        tooltipText: modelData.name + ": " + modelData.count + ". " + modelData.tooltip
        selected: root.selectedTab === modelData.name
        hasCursor: root.activeFocus && root.selectedTab === modelData.name
        focusable: false
        bordered: true
        clip: true
        horizontalPadding: 0
        verticalPadding: 0
        foreground: root.foreground
        fontFamily: root.fontFamily
        fontSize: Style.font.bodySmall
        onClicked: {
          root.forceActiveFocus()
          root.selected(modelData.name)
        }

        Column {
          id: tabContent
          anchors.fill: parent
          anchors.margins: Style.spacing.xs
          spacing: Style.spacing.xxs

          Row {
            width: parent.width
            spacing: Style.spacing.xs

            Text {
              id: tabIconItem
              width: Math.min(implicitWidth, parent.width)
              text: modelData.glyph
              textFormat: Text.PlainText
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.NoWrap
            }

            Text {
              id: tabLabelItem
              width: Math.max(0, parent.width - tabIconItem.width - parent.spacing)
              text: modelData.name + " " + modelData.count
              textFormat: Text.PlainText
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.Wrap
            }
          }

          Text {
            id: tabHealthItem
            width: parent.width
            text: modelData.healthText
            textFormat: Text.PlainText
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.Wrap
          }
        }
      }
    }
  }

  function tabButtonAt(index) { return tabRepeater.itemAt(index) }
  function selectRelative(direction) {
    if (tabButtonCount === 0) return
    var index = tabs.map(function(tab) { return tab.name }).indexOf(selectedTab)
    if (index < 0) index = 0
    root.selected(tabs[(index + direction + tabButtonCount) % tabButtonCount].name)
  }
}
