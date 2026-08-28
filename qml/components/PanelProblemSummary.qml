import QtQuick
import qs.Commons

Item {
  id: root

  property string title: "All sources current"
  property string detail: ""
  property string evidence: ""
  property string glyph: "\uf05e0"
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family

  implicitHeight: content.implicitHeight

  Row {
    id: content
    width: parent.width
    spacing: Style.spacing.sm

    Text {
      width: Style.spacing.controlHeight
      anchors.top: parent.top
      text: root.glyph
      textFormat: Text.PlainText
      color: root.foreground
      font.family: "monospace"
      font.pixelSize: Style.font.body
      horizontalAlignment: Text.AlignHCenter
    }

    Column {
      width: parent.width - Style.spacing.controlHeight - Style.spacing.sm
      spacing: Style.spacing.xs

      Text {
        width: parent.width
        text: root.title
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
        width: parent.width
        visible: root.detail !== ""
        text: root.detail
        textFormat: Text.PlainText
        color: Qt.darker(root.foreground, 1.4)
        font.family: root.fontFamily
        font.pixelSize: Style.font.bodySmall
        wrapMode: Text.Wrap
        maximumLineCount: 3
        elide: Text.ElideRight
      }

      Text {
        width: parent.width
        visible: root.evidence !== ""
        text: root.evidence
        textFormat: Text.PlainText
        color: Qt.darker(root.foreground, 1.4)
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        wrapMode: Text.Wrap
        maximumLineCount: 2
        elide: Text.ElideRight
      }
    }
  }
}
