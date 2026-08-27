import QtQuick

Item {
  id: root
  property string icon: "check"
  property string badge: ""
  property bool stale: false
  property bool refreshing: false
  property color foreground
  property color urgent

  Rectangle {
    visible: root.icon === "shield"
    anchors.centerIn: parent
    width: parent.width * 0.62
    height: parent.height * 0.72
    radius: width * 0.18
    color: root.urgent
  }
  Rectangle {
    visible: root.icon === "bookmark"
    anchors.centerIn: parent
    width: parent.width * 0.56
    height: parent.height * 0.72
    color: root.foreground
  }
  Rectangle {
    visible: root.icon === "update"
    anchors.centerIn: parent
    width: parent.width * 0.72
    height: parent.height * 0.28
    radius: height / 2
    color: root.foreground
  }
  Rectangle {
    visible: root.icon === "warning"
    anchors.centerIn: parent
    width: parent.width * 0.7
    height: parent.height * 0.7
    rotation: 45
    color: root.foreground
  }
  Rectangle {
    visible: root.icon === "check"
    anchors.centerIn: parent
    width: parent.width * 0.7
    height: parent.height * 0.7
    radius: width / 2
    color: root.foreground
  }
  Text {
    visible: root.badge !== ""
    anchors.right: parent.right
    anchors.bottom: parent.bottom
    text: root.badge
    color: root.foreground
    font.bold: true
    font.pixelSize: Math.max(7, parent.width * 0.42)
  }
  Text {
    visible: root.refreshing || root.stale
    anchors.left: parent.left
    anchors.top: parent.top
    text: root.refreshing ? "…" : "↶"
    color: root.foreground
    font.pixelSize: Math.max(6, parent.width * 0.4)
  }
}
