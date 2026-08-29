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
  readonly property Item findingControl: firstFindingControl()
  readonly property Item primaryControl: findingControl ? findingControl : refreshButton
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
      visible: root.findingControl === null
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
        readonly property Item primaryControl: firstControl()
        width: parent.width
        implicitHeight: findings.implicitHeight
        height: implicitHeight

        function firstControl() {
          for (var findingIndex = 0; findingIndex < findingRepeater.count; findingIndex += 1) {
            var row = findingRepeater.itemAt(findingIndex)
            if (row && row.primaryControl) return row.primaryControl
          }
          return null
        }

        Column {
          id: findings
          width: parent.width
          spacing: Style.spacing.sm

          Repeater {
            id: findingRepeater
            model: modelData.findings

            delegate: SecurityFindingRow {
              required property var modelData
              width: parent.width
              group: parent.parent.modelData
              finding: modelData
              starState: root.starState
              confirmedMode: root.watchRow(parent.parent.modelData).watchMode
              watchable: root.watchRow(parent.parent.modelData).watchable
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

  function firstFindingControl() {
    for (var groupIndex = 0; groupIndex < groupRepeater.count; groupIndex += 1) {
      var group = groupRepeater.itemAt(groupIndex)
      if (group && group.primaryControl) return group.primaryControl
    }
    return null
  }
}
