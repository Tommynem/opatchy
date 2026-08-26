import QtQuick

Item {
  id: root

  visible: false

  property bool active: false
  property int refreshInterval: 60000
  readonly property int interval: Math.max(10, Math.min(60000, refreshInterval))
  readonly property double currentTime: clockTime
  property double clockTime: Date.now()

  function tick() {
    clockTime = Date.now()
  }

  Timer {
    interval: root.interval
    repeat: true
    running: root.active
    onTriggered: root.tick()
  }
}
