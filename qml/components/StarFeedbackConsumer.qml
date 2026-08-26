import QtQuick

QtObject {
  id: root

  property var starState: null
  property string target: ""
  property string confirmedMode: "off"
  property bool temporaryArmed: false
  property int activations: 0

  signal activated()

  onConfirmedModeChanged: observe()
  onTemporaryArmedChanged: observe()
  Component.onCompleted: observe()

  function acceptFeedback(changedTarget) {
    if (changedTarget === target) {
      activations += 1
      activated()
    }
  }

  function observe() {
    if (starState && target !== "") starState.observeConfirmed(target, confirmedMode, temporaryArmed)
  }
}
