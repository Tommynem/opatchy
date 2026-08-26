import QtQuick

QtObject {
  id: root

  property var starState: null
  property string target: ""
  property string confirmedMode: "off"
  property bool temporaryArmed: false
  property int activations: 0
  property string observedState: ""

  signal activated()

  onConfirmedModeChanged: observe()
  onTemporaryArmedChanged: observe()
  Component.onCompleted: observedState = currentState()

  function acceptFeedback(changedTarget) {
    if (changedTarget === target) {
      activations += 1
      activated()
    }
  }

  function observe() {
    var current = currentState()
    if (observedState !== "" && observedState !== current) acceptFeedback(target)
    observedState = current
  }

  function currentState() {
    return confirmedMode + ":" + temporaryArmed
  }
}
