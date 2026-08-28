import QtQuick
import qs.Commons
import qs.Ui

Item {
  id: root

  property var rows: []
  property string emptyText: "No actionable updates in this source."
  property var starState: null
  property bool notifyPermanent: true
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family

  implicitHeight: content.implicitHeight

  Column {
    id: content
    width: parent.width
    spacing: Style.spacing.xs

    Text {
      visible: root.rows.length === 0
      width: parent.width
      text: root.emptyText
      textFormat: Text.PlainText
      color: Qt.darker(root.foreground, 1.4)
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
      wrapMode: Text.Wrap
    }

    Repeater {
      model: root.rows

      delegate: UpdateRow {
        required property var modelData
        width: parent.width
        row: modelData
        starState: root.starState
        notifyPermanent: root.notifyPermanent
        foreground: root.foreground
        fontFamily: root.fontFamily
      }
    }
  }
}
