import QtQuick
import qs.Commons
import qs.Ui
import "../models/UpdateViewModel.js" as UpdateViewModel
import "../models/StarViewModel.js" as StarViewModel

FocusScope {
  id: root

  property string tab: "Security"
  property var service: null
  property var snapshot: null
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  property alias browsing: browseMode.browsing
  property bool watchedOnly: false
  property bool notifyPermanent: true
  property bool reducedMotion: false
  property Item previousFocusItem: null
  readonly property alias starState: stars
  readonly property Item primaryControl: tab === "Security" ? securityView.primaryControl : browseButton
  readonly property var rows: UpdateViewModel.updateRows(snapshot, tab)
  readonly property var displayedRows: watchedOnly ? StarViewModel.watchedRows(rows).map(function(watched) {
    return rows.filter(function(row) { return row.target === watched.target })[0]
  }) : rows
  readonly property var actions: UpdateViewModel.footerActions(snapshot, tab, {
    canOpenOmarchyUpdate: service && service.canOpenOmarchyUpdate === true,
    canOpenFlatpakUserUpdate: service && service.canOpenFlatpakUserUpdate === true,
    canOpenFlatpakSystemUpdate: service && service.canOpenFlatpakSystemUpdate === true,
  })

  implicitHeight: content.implicitHeight

  StarInteractionState {
    id: stars
    service: root.service
    snapshotGeneration: root.snapshot && typeof root.snapshot.generationId === "string" ? root.snapshot.generationId : ""
    notifyPermanent: root.notifyPermanent
    reducedMotion: root.reducedMotion
    onReconcileRequested: function(target) {
      if (browseState.source !== "" && target.indexOf(browseState.source + ":") === 0) browseState.queueRequest()
    }
  }

  Column {
    id: content
    width: parent.width
    spacing: Style.spacing.sm

    SecurityView {
      id: securityView
      visible: root.tab === "Security"
      width: parent.width
      snapshot: root.snapshot
      starState: stars
      canRefresh: root.service !== null
      previousFocusItem: root.previousFocusItem
      notifyPermanent: root.notifyPermanent
      foreground: root.foreground
      fontFamily: root.fontFamily
      onRefreshRequested: if (root.service) root.service.requestRefresh()
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
            id: browseButton
            objectName: "browse-primary-control"
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

        BoundedControlStack {
          visible: UpdateViewModel.canBrowse(root.tab)
          width: parent.width
          spacing: Style.spacing.sm

          Button {
            width: parent.width
            text: root.watchedOnly ? "Show all" : "Watched"
            tooltipText: root.watchedOnly ? "Show all available rows" : "Show temporary and permanent watches, including last-known permanent entries"
            foreground: root.foreground
            fontFamily: root.fontFamily
            fontSize: Style.font.bodySmall
            focusable: true
            bordered: true
            onClicked: { root.watchedOnly = !root.watchedOnly; if (root.watchedOnly && !root.browsing) root.toggleBrowse() }
          }
        }

        UpdateListView {
          visible: !root.browsing
          width: parent.width
          rows: root.displayedRows
          emptyTitle: root.watchedOnly ? "No watched items" : "Nothing needs action"
          emptyDetail: root.watchedOnly
            ? "This source has no temporary or permanent watches to review."
            : "This source has no actionable updates in the current evidence."
          starState: stars
          notifyPermanent: root.notifyPermanent
          foreground: root.foreground
          fontFamily: root.fontFamily
        }

        InventoryBrowseView {
          visible: root.browsing
          width: parent.width
          state: browseState
          starState: stars
          notifyPermanent: root.notifyPermanent
          watchedOnly: root.watchedOnly
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

    function onStarResultChanged(result, operation) {
      stars.acceptResult(result, operation)
    }

    function onStarFailed(operation, message) {
      stars.acceptFailure(operation, message)
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
