import QtQuick
import qs.Commons
import qs.Ui

Item {
  id: root

  property var rows: []
  property string emptyTitle: "Nothing needs action"
  property string emptyDetail: "Current source data has no actionable updates."
  property string resultNoun: "updates"
  property var starState: null
  property bool notifyPermanent: true
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  property int viewportHeight: Style.space(180)
  property Item previousFocusItem: null
  property Item nextFocusItem: null
  property int expandedIndex: -1
  property int pendingContainmentIndex: -1
  readonly property alias listControl: list
  readonly property alias verticalScrollBar: verticalScrollBar
  readonly property alias topControl: topButton
  readonly property alias positionCue: positionCue
  readonly property int currentIndex: list.currentIndex
  readonly property int firstVisibleIndex: Math.max(0, list.indexAt(1, list.contentY + 1))
  readonly property int visibleDelegateCount: list.contentItem.children.length

  implicitHeight: root.rows.length === 0 ? emptyContent.implicitHeight : listHeader.height + Style.spacing.xs + viewportHeight
  height: implicitHeight

  Column {
    id: emptyContent
    visible: root.rows.length === 0
    width: parent.width
    spacing: Style.spacing.xs

    Text {
      width: parent.width
      text: root.emptyTitle
      textFormat: Text.PlainText
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
      font.bold: true
      wrapMode: Text.Wrap
      maximumLineCount: 2
      elide: Text.ElideRight
    }

    Text {
      visible: root.emptyDetail !== ""
      width: parent.width
      text: root.emptyDetail
      textFormat: Text.PlainText
      color: Qt.darker(root.foreground, 1.4)
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
      wrapMode: Text.Wrap
      maximumLineCount: 3
      elide: Text.ElideRight
    }
  }

  Item {
    id: listHeader
    visible: root.rows.length > 0
    width: parent.width
    height: Style.spacing.controlHeight

    Text {
      id: positionCue
      objectName: "update-list-position-cue"
      anchors.left: parent.left
      anchors.right: topButton.left
      anchors.rightMargin: Style.spacing.xs
      anchors.verticalCenter: parent.verticalCenter
      text: root.rows.length + " " + root.resultNoun + " | " + (root.firstVisibleIndex + 1) + " of " + root.rows.length
      textFormat: Text.PlainText
      color: Qt.darker(root.foreground, 1.4)
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      elide: Text.ElideRight
      maximumLineCount: 1
    }

    Button {
      id: topButton
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      width: Style.space(42)
      height: Style.spacing.controlHeight
      text: "Top"
      tooltipText: "Return to the first update"
      foreground: root.foreground
      fontFamily: root.fontFamily
      fontSize: Style.font.caption
      focusable: true
      bordered: true
      enabled: list.contentY > 0
      Keys.priority: Keys.BeforeItem
      Keys.onTabPressed: function(event) {
        list.forceActiveFocus()
        event.accepted = true
      }
      Keys.onBacktabPressed: function(event) {
        if (root.previousFocusItem) root.previousFocusItem.forceActiveFocus()
        event.accepted = root.previousFocusItem !== null
      }
      onClicked: root.returnToTop()
    }
  }

  ListView {
    id: list
    objectName: "opatchy-update-list"
    visible: root.rows.length > 0
    anchors.top: listHeader.bottom
    anchors.topMargin: Style.spacing.xs
    width: parent.width
    height: root.viewportHeight
    clip: true
    focus: true
    activeFocusOnTab: true
    model: root.rows
    spacing: Style.spacing.xxs
    reuseItems: true
    cacheBuffer: Style.space(72)
    boundsBehavior: Flickable.StopAtBounds
    flickableDirection: Flickable.VerticalFlick
    keyNavigationEnabled: false
    currentIndex: root.rows.length > 0 ? 0 : -1

    onCurrentIndexChanged: {
      if (root.expandedIndex !== currentIndex) {
        root.pendingContainmentIndex = -1
        root.expandedIndex = -1
      }
    }
    onContentHeightChanged: {
      if (root.pendingContainmentIndex === currentIndex && root.expandedIndex === currentIndex) {
        root.positionRowAfterLayout(root.pendingContainmentIndex, true)
      }
    }
    onMovementStarted: root.pendingContainmentIndex = -1
    Keys.priority: Keys.BeforeItem
    Keys.onPressed: function(event) {
      switch (event.key) {
      case Qt.Key_Up: root.moveToIndex(currentIndex - 1); break
      case Qt.Key_Down: root.moveToIndex(currentIndex + 1); break
      case Qt.Key_PageUp: root.moveToIndex(currentIndex - root.pageStep()); break
      case Qt.Key_PageDown: root.moveToIndex(currentIndex + root.pageStep()); break
      case Qt.Key_Home: root.moveToIndex(0); break
      case Qt.Key_End: root.moveToIndex(count - 1); break
      case Qt.Key_Return:
      case Qt.Key_Enter:
      case Qt.Key_Space: root.activateRow(currentIndex); break
      default: return
      }
      event.accepted = true
    }
    Keys.onReturnPressed: function(event) {
      root.activateRow(currentIndex)
      event.accepted = true
    }
    Keys.onSpacePressed: function(event) {
      root.activateRow(currentIndex)
      event.accepted = true
    }
    Keys.onTabPressed: function(event) {
      root.focusWatchSelectorOrNext()
      event.accepted = true
    }
    Keys.onBacktabPressed: function(event) {
      if (topButton.enabled) {
        topButton.forceActiveFocus()
        event.accepted = true
      } else if (root.previousFocusItem) {
        root.previousFocusItem.forceActiveFocus()
        event.accepted = true
      }
    }

    delegate: UpdateRow {
      id: delegateRoot
      required property int index
      required property var modelData
      objectName: "opatchy-update-row-" + index
      width: list.width - verticalScrollBar.width - Style.spacing.xxs
      row: modelData
      starState: root.starState
      notifyPermanent: root.notifyPermanent
      foreground: root.foreground
      fontFamily: root.fontFamily
      selected: ListView.isCurrentItem
      expanded: root.expandedIndex === index
      listControl: list
      nextFocusItem: root.nextFocusItem
      onActivateRequested: root.activateRow(index)
    }

  }

  BoundedScrollIndicator {
    id: verticalScrollBar
    anchors.top: list.top
    anchors.bottom: list.bottom
    anchors.right: list.right
    flickable: list
  }

  function activateRow(index) {
    if (index < 0 || index >= rows.length) return
    if (list.currentIndex !== index) list.currentIndex = index
    if (expandedIndex === index) {
      pendingContainmentIndex = -1
      expandedIndex = -1
      positionRowAfterLayout(list.currentIndex, false)
      return
    }
    expandRow(index)
  }

  function moveToIndex(index) {
    if (rows.length === 0) return
    list.currentIndex = Math.max(0, Math.min(rows.length - 1, index))
    positionRowAfterLayout(list.currentIndex, false)
  }

  function positionRowAfterLayout(index, requireExpansion) {
    Qt.callLater(function() {
      if (requireExpansion && (pendingContainmentIndex !== index || expandedIndex !== index || list.currentIndex !== index)) return
      list.forceLayout()
      list.positionViewAtIndex(requireExpansion ? index : list.currentIndex, ListView.Contain)
    })
  }

  function expandRow(index) {
    pendingContainmentIndex = index
    expandedIndex = index
  }

  function pageStep() {
    var current = list.currentItem
    var rowHeight = current && current.height > 0 ? current.height + list.spacing : Style.space(36)
    return Math.max(1, Math.floor(list.height / rowHeight))
  }

  function returnToTop() {
    pendingContainmentIndex = -1
    expandedIndex = -1
    moveToIndex(0)
    list.contentY = 0
  }

  function rowAt(index) {
    return list.itemAtIndex(index)
  }

  function focusWatchSelectorOrNext() {
    var current = rowAt(list.currentIndex)
    if (current && current.canClearWatch) { current.watchTrigger.forceActiveFocus(); return }
    if (current && current.row.watchable === true) {
      if (expandedIndex !== list.currentIndex) expandRow(list.currentIndex)
      Qt.callLater(function() { var expandedRow = rowAt(list.currentIndex); if (expandedRow && expandedRow.watchSelector) expandedRow.watchSelector.forceActiveFocus() })
      return
    }
    if (nextFocusItem) nextFocusItem.forceActiveFocus()
  }
}
