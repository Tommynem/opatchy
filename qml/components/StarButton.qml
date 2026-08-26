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
    : ({ glyph: "☆", label: "Not watched", tooltip: "Watch state is unavailable.", accessibleName: "Watch state is unavailable", enabled: false })

  text: view.glyph + " " + view.shortLabel
  tooltipText: view.tooltip
  accessibleName: view.accessibleName
  enabled: view.enabled
  focusable: true
  bordered: true
  onClicked: if (starState) starState.request(target, confirmedMode, watchable)
}
