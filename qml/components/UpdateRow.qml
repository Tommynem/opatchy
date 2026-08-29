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
  property bool selected: false
  property bool expanded: false
  property Item listControl: null
  property Item nextFocusItem: null
  property alias packageLabel: packageLabel
  property alias versionLine: versionLine
  property alias watchTrigger: watchTrigger
  property alias watchSelector: watchSelector

  signal activateRequested()

  implicitHeight: scanLine.height + (expandedDetails.visible ? Style.spacing.xs + expandedDetails.implicitHeight : 0)
  height: implicitHeight

  Column {
    id: details
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.verticalCenter: parent.verticalCenter
    spacing: Style.spacing.xs

    Item {
      id: scanLine
      width: parent.width
      height: Style.space(36)

      Column {
        anchors.left: parent.left
        anchors.right: row.watchable === true ? watchTrigger.left : watchUnavailable.left
        anchors.rightMargin: Style.spacing.xs
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.spacing.xxs

        Text {
          id: packageLabel
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
          id: versionLine
          width: parent.width
          text: presentation.scanText
          textFormat: Text.PlainText
          color: Qt.darker(root.foreground, 1.4)
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
          elide: Text.ElideRight
          maximumLineCount: 1
        }
      }

      MouseArea {
        anchors.left: parent.left
        anchors.right: row.watchable === true ? watchTrigger.left : watchUnavailable.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        onClicked: root.activateRequested()
      }

      StarButton {
        id: watchTrigger
        visible: root.row.watchable === true
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: Style.space(62)
        height: Style.spacing.controlHeight
        starState: root.starState
        target: typeof root.row.target === "string" ? root.row.target : ""
        confirmedMode: typeof root.row.watchMode === "string" ? root.row.watchMode : "off"
        watchable: true
        temporaryArmed: root.row.temporaryArmed === true
        lastKnown: typeof root.row.healthText === "string" && root.row.healthText.indexOf("Last known") !== -1
        notifyPermanent: root.notifyPermanent
        foreground: root.foreground
        fontFamily: root.fontFamily
        fontSize: Style.font.caption
        compact: true
        modeSelectorTrigger: true
        focusable: false
        onModeSelectorRequested: root.activateRequested()
      }

      Text {
        id: watchUnavailable
        visible: root.row.watchable !== true
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        text: "Watch unavailable"
        textFormat: Text.PlainText
        color: Qt.darker(root.foreground, 1.4)
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        elide: Text.ElideRight
        maximumLineCount: 1
      }
    }

    Column {
      id: expandedDetails
      visible: root.expanded
      width: parent.width
      spacing: Style.spacing.xs

      WatchModeSelector {
        id: watchSelector
        visible: root.row.watchable === true
        width: parent.width
        starState: root.starState
        target: typeof root.row.target === "string" ? root.row.target : ""
        confirmedMode: typeof root.row.watchMode === "string" ? root.row.watchMode : "off"
        watchable: true
        previousFocusItem: root.listControl
        nextFocusItem: root.nextFocusItem
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
  }

  UpdateRowPresentation {
    id: presentation
    row: root.row
  }
}
