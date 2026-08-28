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
  property bool canRefresh: false
  property bool notifyPermanent: true
  property Item previousFocusItem: null
  readonly property var view: presentation.view
  readonly property Item primaryControl: groupRepeater.count > 0 && groupRepeater.itemAt(0)
    ? groupRepeater.itemAt(0).primaryControl
    : refreshButton
  signal refreshRequested()

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

    Button {
      id: refreshButton
      objectName: "security-refresh"
      visible: root.view.groups.length === 0
      width: parent.width
      text: "Refresh security data"
      tooltipText: "Request a new source scan; results may remain unavailable."
      foreground: root.foreground
      fontFamily: root.fontFamily
      fontSize: Style.font.bodySmall
      focusable: true
      bordered: true
      enabled: root.canRefresh
      KeyNavigation.backtab: root.previousFocusItem
      Keys.priority: Keys.BeforeItem
      Keys.onTabPressed: function(event) {
        if (event.modifiers !== Qt.ShiftModifier || !root.previousFocusItem) return
        root.previousFocusItem.forceActiveFocus()
        event.accepted = true
      }
      Keys.onPressed: function(event) {
        if (event.key !== Qt.Key_Backtab || !root.previousFocusItem) return
        root.previousFocusItem.forceActiveFocus()
        event.accepted = true
      }
      onClicked: root.refreshRequested()
    }

    Repeater {
      id: groupRepeater
      model: root.view.groups

      delegate: Item {
        required property var modelData
        property alias primaryControl: watchButton
        width: parent.width
        implicitHeight: findings.implicitHeight

        Column {
          id: findings
          width: parent.width
          spacing: Style.spacing.sm

          StarButton {
            id: watchButton
            objectName: "security-watch-" + modelData.watchTarget
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
