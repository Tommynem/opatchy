import QtQuick

Item {
  id: root

  default property alias content: layout.data
  readonly property var controls: layout.children
  property int spacing: 0

  implicitHeight: layout.implicitHeight

  Column {
    id: layout
    width: parent.width
    spacing: root.spacing
  }
}
