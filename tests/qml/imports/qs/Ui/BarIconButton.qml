import QtQuick
import QtQuick.Controls

Button {
  objectName: "opatchy-bar-icon"
  property var bar: null
  property var iconComponent: null
  property string tooltipText: ""
  property color foreground: "black"
  property color activeColor: "red"
  property bool active: false
  property bool dimmed: false
  property string fontFamily: "Sans Serif"
  property real fontSize: 14
}
