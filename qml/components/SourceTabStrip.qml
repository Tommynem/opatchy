import QtQuick
import qs.Commons
import qs.Ui

Item {
  id: root

  property var tabs: []
  property string selectedTab: "Security"
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  signal selected(string tab)

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
        focusable: true
        bordered: true
        clip: true
        horizontalPadding: 0
        verticalPadding: 0
        foreground: root.foreground
        fontFamily: root.fontFamily
        fontSize: Style.font.bodySmall
        onClicked: root.selected(modelData.name)

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
}
