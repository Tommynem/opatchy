import QtQuick
import QtQuick.Shapes

Item {
  id: root
  property string icon: "check"
  property string badge: ""
  property bool stale: false
  property bool refreshing: false
  property color foreground
  property color urgent

  Shape {
    anchors.fill: parent
    visible: root.icon === "shield"
    ShapePath { fillColor: root.urgent; strokeColor: "transparent"; startX: width * .5; startY: height * .06; PathLine { x: width * .84; y: height * .2 }; PathLine { x: width * .76; y: height * .68 }; PathLine { x: width * .5; y: height * .92 }; PathLine { x: width * .24; y: height * .68 }; PathLine { x: width * .16; y: height * .2 }; PathLine { x: width * .5; y: height * .06 } }
  }
  Text { visible: root.icon === "shield"; anchors.centerIn: parent; text: "!"; color: root.foreground; font.bold: true; font.pixelSize: parent.width * .48 }

  Shape {
    anchors.fill: parent
    visible: root.icon === "bookmark"
    ShapePath { fillColor: root.foreground; strokeColor: "transparent"; startX: width * .24; startY: height * .1; PathLine { x: width * .76; y: height * .1 }; PathLine { x: width * .76; y: height * .9 }; PathLine { x: width * .5; y: height * .7 }; PathLine { x: width * .24; y: height * .9 }; PathLine { x: width * .24; y: height * .1 } }
  }

  Rectangle { visible: root.icon === "update"; anchors.centerIn: parent; width: parent.width * .72; height: parent.height * .5; radius: width * .08; color: root.foreground }
  Rectangle { visible: root.icon === "update"; anchors.horizontalCenter: parent.horizontalCenter; y: parent.height * .04; width: parent.width * .16; height: parent.height * .48; color: root.foreground }
  Shape { anchors.fill: parent; visible: root.icon === "update"; ShapePath { fillColor: root.foreground; strokeColor: "transparent"; startX: width * .3; startY: height * .34; PathLine { x: width * .7; y: height * .34 }; PathLine { x: width * .5; y: height * .08 }; PathLine { x: width * .3; y: height * .34 } } }

  Shape { anchors.fill: parent; visible: root.icon === "warning"; ShapePath { fillColor: root.foreground; strokeColor: "transparent"; startX: width * .5; startY: height * .08; PathLine { x: width * .92; y: height * .86 }; PathLine { x: width * .08; y: height * .86 }; PathLine { x: width * .5; y: height * .08 } } }
  Text { visible: root.icon === "warning"; anchors.centerIn: parent; text: "!"; color: root.urgent; font.bold: true; font.pixelSize: parent.width * .46 }

  Rectangle { visible: root.icon === "check"; anchors.centerIn: parent; width: parent.width * .76; height: width; radius: width / 2; border.width: Math.max(1, width * .12); border.color: root.foreground; color: "transparent" }
  Rectangle { visible: root.icon === "check"; x: parent.width * .25; y: parent.height * .53; width: parent.width * .23; height: Math.max(1, parent.width * .12); rotation: 42; color: root.foreground }
  Rectangle { visible: root.icon === "check"; x: parent.width * .43; y: parent.height * .43; width: parent.width * .38; height: Math.max(1, parent.width * .12); rotation: -45; color: root.foreground }

  Text { visible: root.badge !== ""; anchors.right: parent.right; anchors.bottom: parent.bottom; text: root.badge; color: root.foreground; font.bold: true; font.pixelSize: Math.max(7, parent.width * .42) }
  Text { visible: root.refreshing || root.stale; anchors.left: parent.left; anchors.top: parent.top; text: root.refreshing ? "…" : "↶"; color: root.foreground; font.pixelSize: Math.max(6, parent.width * .4) }
}
