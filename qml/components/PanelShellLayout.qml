import QtQml

QtObject {
  property string edge: "top"
  property real screenWidth: 0
  property real screenHeight: 0
  property real barExtent: 0
  property real gap: 0
  property real margin: 0
  property real availableWidth: 0
  property real availableHeight: 0
  property real preferredWidth: 1
  property real preferredHeight: 1

  readonly property bool vertical: edge === "left" || edge === "right"
  readonly property real edgeAvailableWidth: vertical
    ? screenWidth - barExtent - gap - margin * 2
    : screenWidth - margin * 2
  readonly property real edgeAvailableHeight: vertical
    ? screenHeight - margin * 2
    : screenHeight - barExtent - gap - margin * 2
  readonly property real boundedAvailableWidth: availableWidth > 0
    ? availableWidth
    : edgeAvailableWidth
  readonly property real boundedAvailableHeight: availableHeight > 0
    ? availableHeight
    : edgeAvailableHeight
  readonly property real contentWidth: bounded(preferredWidth, boundedAvailableWidth)
  readonly property real contentHeight: bounded(preferredHeight, boundedAvailableHeight)

  function bounded(preferred, available) {
    var desired = Math.max(1, Number(preferred) || 1)
    return available > 0 ? Math.min(desired, available) : desired
  }
}
