import QtQuick 2.15

Item {
  id: root
  property string icon: "check"
  property string badge: ""
  property bool stale: false
  property bool refreshing: false
  property color foreground
  property color urgent
  property string fontFamily: "monospace"
  property real fontSize: 13
  readonly property string glyph: glyphFor(icon)
  readonly property color glyphColor: icon === "shield" ? root.urgent : root.foreground
  readonly property int renderedFontSize: Math.max(1, Math.round(fontSize))
  readonly property real tightWidth: Math.max(1, glyphMetrics.tightBoundingRect.width)
  readonly property real horizontalCorrection: primaryGlyph.implicitWidth / 2 - (glyphMetrics.tightBoundingRect.x + tightWidth / 2)

  function glyphFor(currentIcon) {
    if (currentIcon === "shield") return "󰕥"
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
    anchors.centerIn: parent
    anchors.horizontalCenterOffset: root.horizontalCorrection
    text: root.glyph
    color: root.glyphColor
    font.family: root.fontFamily
    font.pixelSize: root.renderedFontSize
    renderType: Text.NativeRendering
  }

  Text { visible: root.badge !== ""; anchors.right: parent.right; anchors.bottom: parent.bottom; text: root.badge; color: root.foreground; font.family: root.fontFamily; font.bold: true; font.pixelSize: Math.max(7, root.fontSize * .54) }
  Text { visible: root.refreshing || root.stale; anchors.left: parent.left; anchors.top: parent.top; text: root.refreshing ? "…" : "↶"; color: root.foreground; font.family: root.fontFamily; font.pixelSize: Math.max(6, root.fontSize * .4) }
}
