import QtQuick
import qs.Ui

Item {
  id: root

  property var tabs: []
  property string selectedTab: "Security"
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  signal selected(string tab)

  implicitHeight: Style.spacing.controlHeight

  ListView {
    id: list
    anchors.fill: parent
    clip: true
    orientation: ListView.Horizontal
    spacing: Style.spacing.sm
    model: root.tabs
    boundsBehavior: Flickable.StopAtBounds
    flickableDirection: Flickable.HorizontalFlick

    delegate: Button {
      required property var modelData

      text: modelData.name + " " + modelData.count + " " + modelData.healthText
      iconText: modelData.glyph
      tooltipText: modelData.name + ": " + modelData.count + ". " + modelData.tooltip
      selected: root.selectedTab === modelData.name
      focusable: true
      bordered: true
      foreground: root.foreground
      fontFamily: root.fontFamily
      fontSize: Style.font.bodySmall
      onClicked: root.selected(modelData.name)
      onActiveFocusChanged: if (activeFocus) list.positionViewAtIndex(index, ListView.Contain)
    }
  }
}
