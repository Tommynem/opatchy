import QtQuick
import qs.Commons
import qs.Ui

Item {
  id: root

  property var row: ({})
  property var starState: null
  property bool notifyPermanent: true
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

    StarButton {
      width: parent.width
      starState: root.starState
      target: typeof root.row.target === "string" ? root.row.target : ""
      confirmedMode: typeof root.row.watchMode === "string" ? root.row.watchMode : "off"
      watchable: root.row.watchable === true
      temporaryArmed: root.row.temporaryArmed === true
      lastKnown: typeof root.row.healthText === "string" && root.row.healthText.indexOf("Last known") !== -1
      notifyPermanent: root.notifyPermanent
      foreground: root.foreground
      fontFamily: root.fontFamily
      fontSize: Style.font.bodySmall
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
