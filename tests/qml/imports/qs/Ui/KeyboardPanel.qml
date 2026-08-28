import QtQuick

Item {
  id: root
  property var anchorItem: null
  property var owner: null
  property var bar: null
  property bool open: false
  property var focusTarget: null
  property real contentWidth: 1
  property real contentHeight: 1
  property string barPos: "top"
  property real availableCardWidth: 520
  property real availableCardHeight: 360

  function fittedContentWidth(value) { return Math.min(value, availableCardWidth) }
  function fittedContentHeight(value) { return Math.min(value, availableCardHeight) }
}
