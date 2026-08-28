import QtQuick
import qs.Commons
import qs.Ui

Item {
  id: root

  property var snapshot: null
  readonly property double currentTime: clock.currentTime
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  property var starState: null
  property bool notifyPermanent: true
  readonly property var view: presentation.view

  implicitHeight: content.implicitHeight

  SecurityClock {
    id: clock
    active: root.visible
  }

  Column {
    id: content
    width: parent.width
    spacing: Style.spacing.sm

    Text {
      width: parent.width
      text: root.view.statusText
      textFormat: Text.PlainText
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
      wrapMode: Text.Wrap
      maximumLineCount: 3
      elide: Text.ElideRight
    }

    Text {
      width: parent.width
      text: root.view.archCoverage.text + "; observed " + root.view.archCoverage.ageText + ". " + root.view.kevCoverage.text + "; observed " + root.view.kevCoverage.ageText + "."
      textFormat: Text.PlainText
      color: Qt.darker(root.foreground, 1.4)
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.Wrap
      maximumLineCount: 3
      elide: Text.ElideRight
    }

    Repeater {
      model: root.view.groups

      delegate: Item {
        required property var modelData
        width: parent.width
        implicitHeight: findings.implicitHeight

        Column {
          id: findings
          width: parent.width
          spacing: Style.spacing.sm

          StarButton {
            width: parent.width
            starState: root.starState
            target: modelData.watchTarget
              confirmedMode: root.watchRow(modelData).watchMode
              temporaryArmed: root.watchRow(modelData).watchArmed
            watchable: root.watchRow(modelData).watchable
            lastKnown: root.view.kind === "last_known"
            notifyPermanent: root.notifyPermanent
            foreground: root.foreground
            fontFamily: root.fontFamily
            fontSize: Style.font.bodySmall
          }

          Repeater {
            model: modelData.findings

            delegate: SecurityFindingRow {
              required property var modelData
              width: parent.width
              group: parent.parent.modelData
              finding: modelData
              foreground: root.foreground
              fontFamily: root.fontFamily
            }
          }
        }
      }
    }
  }

  SecurityViewPresentation {
    id: presentation
    snapshot: root.snapshot
    currentTime: root.currentTime
  }

  function watchRow(group) {
    var items = snapshot && snapshot.payload && Array.isArray(snapshot.payload.items) ? snapshot.payload.items : []
    var item = items.filter(function(candidate) { return candidate && candidate.id === group.watchTarget })[0]
    return item ? { watchMode: item.watchMode, watchArmed: item.watchArmed === true, watchable: item.watchable === true } : { watchMode: "off", watchArmed: false, watchable: false }
  }
}
