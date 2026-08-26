import QtQuick

Item {
  id: root

  visible: false

  property bool active: false
  property int refreshInterval: 60000
  readonly property int interval: Math.max(10, Math.min(60000, refreshInterval))
  readonly property double currentTime: _clockTime
  property double _clockTime: Date.now()

  function tick() {
    _clockTime = Date.now()
  }

  onActiveChanged: if (active) tick()

  Timer {
    interval: root.interval
    repeat: true
    running: root.active
    onTriggered: root.tick()
  }
}
