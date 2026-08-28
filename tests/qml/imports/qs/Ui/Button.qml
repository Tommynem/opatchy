import QtQuick
import QtQuick.Controls

Button {
  property string tooltipText: ""
  property string iconText: ""
  property string placeholderText: ""
  property bool focusable: true
  property bool bordered: true
  property bool selected: false
  property bool hasCursor: false
  property color foreground: "black"
  property string fontFamily: ""
  property real fontSize: 12
  signal textEdited()

  activeFocusOnTab: focusable
}
