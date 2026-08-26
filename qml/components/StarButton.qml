import QtQuick
import qs.Ui

Button {
  id: root

  property var starState: null
  property string target: ""
  property string confirmedMode: "off"
  property bool watchable: false
  property bool temporaryArmed: false
  property bool lastKnown: false
  property bool notifyPermanent: true
  readonly property var view: starState
    ? starState.stateFor(target, confirmedMode, watchable, temporaryArmed, lastKnown)
    : ({ glyph: "☆", shortLabel: "Unavailable", label: "Not watched", tooltip: "Watch state is unavailable.", accessibleName: "Watch state is unavailable", enabled: false, errorText: "" })

  text: view.pending ? "… Updating " + view.shortLabel : view.glyph + " " + view.shortLabel
  tooltipText: view.tooltip
  accessibleName: view.accessibleName
  enabled: view.enabled
  opacity: view.pending ? 0.72 : 1
  focusable: true
  bordered: true
  onClicked: if (starState) starState.request(target, confirmedMode, watchable)

  Behavior on opacity {
    NumberAnimation {
      duration: root.starState && root.starState.reducedMotion ? 0 : 100
    }
  }

  Text {
    visible: root.view.errorText !== ""
    anchors.top: parent.bottom
    width: parent.width
    text: root.view.errorText
    textFormat: Text.PlainText
    color: root.foreground
    wrapMode: Text.Wrap
  }
}
