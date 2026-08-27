import QtQuick 2.15
import QtQuick.Shapes 1.15

Item {
  id: root
  property string icon: "check"
  property string badge: ""
  property bool stale: false
  property bool refreshing: false
  property color foreground
  property color urgent
  Item { id: canvas; anchors.fill: root }
  Shape {
    anchors.fill: canvas; visible: root.icon === "shield"
    ShapePath {
      fillColor: root.urgent; strokeColor: "transparent"
      startX: canvas.width * .5; startY: canvas.height * .06
      PathLine { x: canvas.width * .84; y: canvas.height * .2 }
      PathLine { x: canvas.width * .76; y: canvas.height * .68 }
      PathLine { x: canvas.width * .5; y: canvas.height * .92 }
      PathLine { x: canvas.width * .24; y: canvas.height * .68 }
      PathLine { x: canvas.width * .16; y: canvas.height * .2 }
      PathLine { x: canvas.width * .5; y: canvas.height * .06 }
    }
  }
  Text { visible: root.icon === "shield"; anchors.centerIn: canvas; text: "!"; color: root.foreground; font.bold: true; font.pixelSize: canvas.width * .48 }
  Shape {
    anchors.fill: canvas; visible: root.icon === "bookmark"
    ShapePath {
      fillColor: root.foreground; strokeColor: "transparent"
      startX: canvas.width * .24; startY: canvas.height * .1
      PathLine { x: canvas.width * .76; y: canvas.height * .1 }
      PathLine { x: canvas.width * .76; y: canvas.height * .9 }
      PathLine { x: canvas.width * .5; y: canvas.height * .7 }
      PathLine { x: canvas.width * .24; y: canvas.height * .9 }
      PathLine { x: canvas.width * .24; y: canvas.height * .1 }
    }
  }
  Rectangle { visible: root.icon === "update"; anchors.centerIn: canvas; width: canvas.width * .72; height: canvas.height * .5; radius: canvas.width * .08; color: root.foreground }
  Text { visible: root.icon === "update"; anchors.centerIn: canvas; text: "↑"; color: root.foreground; font.bold: true; font.pixelSize: canvas.width * .7 }
  Shape {
    anchors.fill: canvas; visible: root.icon === "warning"
    ShapePath {
      fillColor: root.foreground; strokeColor: "transparent"
      startX: canvas.width * .5; startY: canvas.height * .08
      PathLine { x: canvas.width * .92; y: canvas.height * .86 }
      PathLine { x: canvas.width * .08; y: canvas.height * .86 }
      PathLine { x: canvas.width * .5; y: canvas.height * .08 }
    }
  }
  Text { visible: root.icon === "warning"; anchors.centerIn: canvas; text: "!"; color: root.foreground; font.bold: true; font.pixelSize: canvas.width * .46 }
  Rectangle { visible: root.icon === "check"; anchors.centerIn: canvas; width: canvas.width * .76; height: width; radius: width / 2; border.width: Math.max(1, width * .12); border.color: root.foreground; color: "transparent" }
  Text { visible: root.icon === "check"; anchors.centerIn: canvas; text: "✓"; color: root.foreground; font.bold: true; font.pixelSize: canvas.width * .62 }
  Text { visible: root.badge !== ""; anchors.right: canvas.right; anchors.bottom: canvas.bottom; text: root.badge; color: root.foreground; font.bold: true; font.pixelSize: Math.max(7, canvas.width * .42) }
  Text { visible: root.refreshing || root.stale; anchors.left: canvas.left; anchors.top: canvas.top; text: root.refreshing ? "…" : "↶"; color: root.foreground; font.pixelSize: Math.max(6, canvas.width * .4) }
}
