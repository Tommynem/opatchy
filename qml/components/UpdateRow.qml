import QtQuick
import qs.Ui

Item {
  id: root

  property var row: ({})
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family

  implicitHeight: details.implicitHeight + Style.spacing.controlPaddingY * 2

  Column {
    id: details
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.verticalCenter: parent.verticalCenter
    spacing: Style.spacing.xs

    Text {
      width: parent.width
      text: presentation.label
      textFormat: Text.PlainText
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
      elide: Text.ElideRight
      maximumLineCount: 1
    }

    Text {
      width: parent.width
      text: presentation.detailsText
      textFormat: Text.PlainText
      color: Qt.darker(root.foreground, 1.4)
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
      elide: Text.ElideRight
      maximumLineCount: 1
    }

    Text {
      width: parent.width
      text: presentation.metaText
      textFormat: Text.PlainText
      color: Qt.darker(root.foreground, 1.4)
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      elide: Text.ElideRight
      maximumLineCount: 1
    }

    Text {
      width: parent.width
      text: presentation.identity
      textFormat: Text.PlainText
      color: Qt.darker(root.foreground, 1.4)
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      elide: Text.ElideRight
      maximumLineCount: 1
    }
  }

  UpdateRowPresentation {
    id: presentation
    row: root.row
  }
}
