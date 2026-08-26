import QtQuick
import qs.Ui
import "../models/UpdateViewModel.js" as UpdateViewModel

Item {
  id: root

  property var state: null
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  readonly property var view: presentation.view

  implicitHeight: content.implicitHeight

  Column {
    id: content
    width: parent.width
    spacing: Style.spacing.sm

    TextField {
      width: parent.width
      foreground: root.foreground
      placeholderText: "Search cached packages and tools"
      text: root.state ? root.state.query : ""
      onTextEdited: if (root.state) root.state.setQuery(text)
    }

    Text {
      width: parent.width
      text: root.state && root.state.statusText !== "" ? root.state.statusText : root.view.summaryText
      textFormat: Text.PlainText
      color: Qt.darker(root.foreground, 1.4)
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
      wrapMode: Text.Wrap
    }

    UpdateListView {
      width: parent.width
      rows: root.view.rows
      emptyText: ""
      foreground: root.foreground
      fontFamily: root.fontFamily
    }

    BoundedControlStack {
      visible: root.view.kind === "ready" && root.view.total > 0
      width: parent.width
      spacing: Style.spacing.sm

      Button {
        width: parent.width
        text: "Previous"
        tooltipText: "Show the previous 100 cached results"
        foreground: root.foreground
        fontFamily: root.fontFamily
        fontSize: Style.font.bodySmall
        focusable: true
        bordered: true
        enabled: root.state && root.state.offset > 0
        onClicked: root.state.previousPage()
      }

      Text {
        width: parent.width
        text: root.pageText()
        textFormat: Text.PlainText
        color: Qt.darker(root.foreground, 1.4)
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        wrapMode: Text.Wrap
      }

      Button {
        width: parent.width
        text: "Next"
        tooltipText: "Show the next 100 cached results"
        foreground: root.foreground
        fontFamily: root.fontFamily
        fontSize: Style.font.bodySmall
        focusable: true
        bordered: true
        enabled: root.state && root.state.offset + UpdateViewModel.PAGE_SIZE < root.view.total
        onClicked: root.state.nextPage(root.view.total)
      }
    }
  }

  InventoryBrowsePresentation {
    id: presentation
    state: root.state
  }

  function pageText() {
    if (!state || view.total === 0) return ""
    var first = state.offset + 1
    var last = Math.min(state.offset + view.rows.length, view.total)
    return "Showing " + first + "-" + last + " of " + view.total
  }
}
