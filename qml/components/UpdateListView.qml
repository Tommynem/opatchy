import QtQuick
import qs.Commons
import qs.Ui

Item {
  id: root

  property var rows: []
  property string emptyTitle: "Nothing needs action"
  property string emptyDetail: "Current source data has no actionable updates."
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
      text: root.emptyTitle
      textFormat: Text.PlainText
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
      font.bold: true
      wrapMode: Text.Wrap
      maximumLineCount: 2
      elide: Text.ElideRight
    }

    Text {
      visible: root.rows.length === 0 && root.emptyDetail !== ""
      width: parent.width
      text: root.emptyDetail
      textFormat: Text.PlainText
      color: Qt.darker(root.foreground, 1.4)
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
      wrapMode: Text.Wrap
      maximumLineCount: 3
      elide: Text.ElideRight
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
