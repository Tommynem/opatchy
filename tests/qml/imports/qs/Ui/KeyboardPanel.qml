import QtQuick

Item {
  id: root
  objectName: "opatchy-host-keyboard-panel"
  default property alias contentItem: contentHolder.children
  property var anchorItem: null
  property var owner: null
  property var bar: null
  property bool open: false
  property var focusTarget: null
  property real contentWidth: 1
  property real contentHeight: 1
  property string barPos: "top"
  property bool anchorReady: false
  property bool cardReady: false
  property bool openedBeforeGeometry: false
  property real cardInset: 12
  readonly property bool geometryReady: anchorReady && cardReady
  readonly property real availableCardWidth: geometryReady && bar
    ? bar.hostCardWidth
    : 0
  readonly property real availableCardHeight: geometryReady && bar
    ? bar.hostCardHeight
    : 0
  readonly property real committedCardWidth: open && geometryReady && !openedBeforeGeometry
    ? fittedContentWidth(contentWidth)
    : cardInset * 2
  readonly property real committedCardHeight: open && geometryReady && !openedBeforeGeometry
    ? fittedContentHeight(contentHeight)
    : cardInset * 2

  function fittedContentWidth(value) {
    return Math.min(value, availableCardWidth)
  }

  function fittedContentHeight(value) {
    return Math.min(value, availableCardHeight)
  }

  function deferHostGeometry() {
    anchorReady = false
    cardReady = false
    Qt.callLater(function() {
      if (!root.anchorItem || !root.bar) return
      root.anchorReady = true
      Qt.callLater(function() {
        if (root.anchorItem && root.bar) root.cardReady = true
      })
    })
  }

  onAnchorItemChanged: deferHostGeometry()
  onBarChanged: deferHostGeometry()
  onOpenChanged: {
    if (open && !geometryReady) openedBeforeGeometry = true
    if (!open) openedBeforeGeometry = false
  }

  Item {
    id: card
    objectName: "opatchy-host-card"
    width: root.committedCardWidth
    height: root.committedCardHeight

    Item {
      id: contentHolder
      objectName: "opatchy-host-content"
      anchors.fill: parent
      anchors.margins: root.cardInset
    }
  }
}
