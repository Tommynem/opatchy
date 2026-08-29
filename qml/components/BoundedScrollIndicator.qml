import QtQuick
import qs.Commons

Item {
  id: root

  property Flickable flickable: null
  readonly property real position: {
    if (!flickable || flickable.contentHeight <= flickable.height) return 0
    return Math.max(0, Math.min(1, flickable.contentY / (flickable.contentHeight - flickable.height)))
  }
  readonly property real thumbHeight: {
    if (!flickable || flickable.contentHeight <= 0) return height
    return Math.min(height, Math.max(Style.space(16), height * flickable.height / flickable.contentHeight))
  }

  implicitWidth: Style.space(4)
  visible: flickable !== null

  Rectangle {
    width: parent.width
    height: root.thumbHeight
    y: (parent.height - height) * root.position
    radius: width / 2
    color: Color.foreground
    opacity: 0.55
  }
}
