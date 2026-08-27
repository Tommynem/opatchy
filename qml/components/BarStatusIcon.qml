import QtQuick 2.15

Item {
  id: root
  property string icon: "check"
  property string badge: ""
  property bool stale: false
  property bool refreshing: false
  property bool reducedMotion: false
  property color foreground
  property color urgent
  property string fontFamily: "monospace"
  property real fontSize: 13
  readonly property string glyph: glyphFor(icon)
  readonly property color glyphColor: icon === "shield" ? root.urgent : root.foreground
  readonly property int renderedFontSize: Math.max(1, Math.round(fontSize))
  readonly property real badgeFontSize: Math.max(9, root.fontSize * .69)
  readonly property real secondaryFontSize: Math.max(8, Math.round(root.fontSize * .62))
  readonly property real tightWidth: Math.max(1, glyphMetrics.tightBoundingRect.width)
  readonly property real horizontalCorrection: primaryGlyph.implicitWidth / 2 - (glyphMetrics.tightBoundingRect.x + tightWidth / 2)

  function glyphFor(currentIcon) {
    if (currentIcon === "shield") return "󰻌"
    if (currentIcon === "bookmark") return "󰃀"
    if (currentIcon === "update") return "󰏖"
    if (currentIcon === "warning") return "󰀦"
    return "󰗠"
  }

  TextMetrics {
    id: glyphMetrics
    font.family: root.fontFamily
    font.pixelSize: root.renderedFontSize
    text: root.glyph
  }

  Text {
    id: primaryGlyph
    objectName: "primaryGlyph"
    anchors.centerIn: parent
    anchors.horizontalCenterOffset: root.horizontalCorrection
    text: root.glyph
    color: root.glyphColor
    font.family: root.fontFamily
    font.pixelSize: root.renderedFontSize
    renderType: Text.NativeRendering
  }

  Text {
    id: statusBadge
    objectName: "statusBadge"
    visible: root.badge !== ""
    anchors.right: parent.right
    anchors.bottom: parent.bottom
    anchors.rightMargin: -4.5
    anchors.bottomMargin: 0
    text: root.badge
    color: root.foreground
    font.family: root.fontFamily
    font.bold: true
    font.pixelSize: root.badgeFontSize
  }
  Text {
    id: staleMarker
    objectName: "staleMarker"
    visible: root.stale
    anchors.left: parent.left
    anchors.top: parent.top
    anchors.leftMargin: -5.25
    anchors.topMargin: -5
    text: "󰅐"
    color: root.foreground
    font.family: root.fontFamily
    font.pixelSize: root.secondaryFontSize
    renderType: Text.NativeRendering
  }

  Text {
    id: refreshIndicator
    objectName: "refreshIndicator"
    visible: root.refreshing
    anchors.right: parent.right
    anchors.top: parent.top
    anchors.rightMargin: -4.5
    anchors.topMargin: -5
    rotation: root.refreshing && !root.reducedMotion ? root.refreshAngle : 0
    text: "󰑐"
    color: root.foreground
    font.family: root.fontFamily
    font.pixelSize: root.secondaryFontSize
    renderType: Text.NativeRendering
  }

  property real refreshAngle: 0

  NumberAnimation on refreshAngle {
    id: refreshRotation
    objectName: "refreshRotation"
    from: 0
    to: 360
    duration: 900
    loops: Animation.Infinite
    running: root.refreshing && !root.reducedMotion
  }
}
