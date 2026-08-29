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
  property bool compact: false
  property bool modeSelectorTrigger: false
  readonly property var view: starState
    ? starState.stateFor(target, confirmedMode, watchable, temporaryArmed, lastKnown)
    : ({ glyph: "☆", shortLabel: "Unavailable", label: "Not watched", tooltip: "Watch state is unavailable.", accessibleName: "Watch state is unavailable", enabled: false, errorText: "" })

  text: view.pending ? "… Updating " + view.shortLabel : (compact ? view.shortLabel : view.glyph + " " + view.shortLabel)
  tooltipText: view.tooltip
  enabled: view.enabled
  opacity: 1
  focusable: true
  bordered: true
  signal modeSelectorRequested()
  onClicked: {
    if (modeSelectorTrigger) modeSelectorRequested()
    else if (starState) starState.request(target, confirmedMode, watchable)
  }

  StarFeedbackConsumer {
    id: feedbackConsumer
    starState: root.starState
    target: root.target
    confirmedMode: root.confirmedMode
    temporaryArmed: root.temporaryArmed
    onActivated: feedback.restart()
  }

  Connections {
    target: root.starState
    function onFeedbackRequested(target) { feedbackConsumer.acceptFeedback(target) }
  }

  SequentialAnimation {
    id: feedback
    running: false
    NumberAnimation { target: root; property: "opacity"; to: 0.72; duration: root.starState ? root.starState.feedbackDuration / 2 : 50 }
    NumberAnimation { target: root; property: "opacity"; to: 1; duration: root.starState ? root.starState.feedbackDuration / 2 : 50 }
  }

}
