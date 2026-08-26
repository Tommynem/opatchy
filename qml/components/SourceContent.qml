import QtQuick
import qs.Ui
import "../models/UpdateViewModel.js" as UpdateViewModel

Item {
  id: root

  property string tab: "Security"
  property var service: null
  property var snapshot: null
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  property alias browsing: browseMode.browsing
  readonly property var rows: UpdateViewModel.updateRows(snapshot, tab)
  readonly property var actions: UpdateViewModel.footerActions(snapshot, tab, {
    canOpenOmarchyUpdate: service && service.canOpenOmarchyUpdate === true,
    canOpenFlatpakUserUpdate: service && service.canOpenFlatpakUserUpdate === true,
    canOpenFlatpakSystemUpdate: service && service.canOpenFlatpakSystemUpdate === true,
  })

  implicitHeight: content.implicitHeight

  Column {
    id: content
    width: parent.width
    spacing: Style.spacing.sm

    SecurityView {
      visible: root.tab === "Security"
      width: parent.width
      snapshot: root.snapshot
      foreground: root.foreground
      fontFamily: root.fontFamily
    }

    Item {
      visible: root.tab !== "Security"
      width: parent.width
      implicitHeight: contentColumn.implicitHeight

      Column {
        id: contentColumn
        width: parent.width
        spacing: Style.spacing.sm

        BoundedControlStack {
          visible: UpdateViewModel.canBrowse(root.tab)
          width: parent.width
          spacing: Style.spacing.sm

          Button {
            width: parent.width
            text: root.browsing ? "Show updates" : "Browse packages/tools"
            tooltipText: root.browsing ? "Show actionable updates" : "Search cached packages and tools"
            foreground: root.foreground
            fontFamily: root.fontFamily
            fontSize: Style.font.bodySmall
            focusable: true
            bordered: true
            onClicked: root.toggleBrowse()
          }
        }

        UpdateListView {
          visible: !root.browsing
          width: parent.width
          rows: root.rows
          foreground: root.foreground
          fontFamily: root.fontFamily
        }

        InventoryBrowseView {
          visible: root.browsing
          width: parent.width
          state: browseState
          foreground: root.foreground
          fontFamily: root.fontFamily
        }

        BoundedControlStack {
          visible: root.actions.length > 0
          width: parent.width
          spacing: Style.spacing.sm

          Repeater {
            model: root.actions

            delegate: Button {
              required property var modelData
              width: parent.width
              text: modelData.text
              tooltipText: modelData.text
              foreground: root.foreground
              fontFamily: root.fontFamily
              fontSize: Style.font.bodySmall
              focusable: true
              bordered: true
              enabled: modelData.enabled
              onClicked: root.dispatch(modelData.kind)
            }
          }
        }
      }
    }
  }

  InventoryBrowseState {
    id: browseState
    service: root.service
    generationId: root.snapshot && typeof root.snapshot.generationId === "string" ? root.snapshot.generationId : ""
  }

  BrowseModeState {
    id: browseMode
    tab: root.tab
  }

  Connections {
    target: root.service

    function onInventoryChanged(source, inventory, operation) {
      browseState.acceptInventory(source, inventory, operation)
    }
  }

  function toggleBrowse() {
    browsing = !browsing
    if (browsing) browseState.open(UpdateViewModel.inventorySourceForTab(tab))
  }

  function dispatch(kind) {
    if (!service) return
    switch (kind) {
    case "omarchy": service.openOmarchyUpdate(); break
    case "flatpak-user": service.openFlatpakUserUpdate(); break
    case "flatpak-system": service.openFlatpakSystemUpdate(); break
    }
  }
}
