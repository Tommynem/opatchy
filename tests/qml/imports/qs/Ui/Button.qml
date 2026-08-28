import QtQuick
import QtQuick.Controls
import qs.Commons

Button {
  id: root
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

  font.family: fontFamily
  font.pixelSize: fontSize
  leftPadding: Style.spacing.controlPaddingX
  rightPadding: Style.spacing.controlPaddingX
  topPadding: Style.spacing.controlPaddingY
  bottomPadding: Style.spacing.controlPaddingY
  activeFocusOnTab: focusable
}
