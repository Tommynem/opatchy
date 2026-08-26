import QtQuick
import qs.Ui
import "qml/components"
import "qml/models/TabModel.js" as TabModel

Panel {
  id: root
  moduleName: "io.github.tomge.opatchy"
  manageIpc: false

  property var shell: null
  property var manifest: null
  property var anchorItem: null
  property var hostWidget: null
  property var injectedService: null
  readonly property var barIdentity: hostWidget || root
  readonly property var service: injectedService !== null
    ? injectedService
    : lifecycleState.service
  readonly property bool serviceAvailable: service !== null
  readonly property string statusText: serviceAvailable
    ? "Opatchy"
    : "Service unavailable"
  readonly property bool urgentSecurity: TabModel.hasUrgentSecurity(service ? service.lastSnapshot : null)
  readonly property var panelView: TabModel.buildPanelState(service ? service.lastSnapshot : null, {
    "refreshing": service ? service.refreshing : false,
    "lastAttemptAt": service ? service.lastAttemptAt : null,
    "lastSuccessAt": service ? service.lastSuccessAt : null,
    "lastFailureKind": service ? service.lastFailureKind : "",
  }, Date.now())

  LifecycleState {
    id: lifecycleState
    shell: root.shell
    manifest: root.manifest
  }

  PanelShellState {
    id: panelState
    service: root.service
    anchorItem: root.anchorItem
  }

  function close() {
    controller.hide()
    Qt.callLater(panelState.returnFocus)
  }

  function persistSelectedTab(tab) {
    TabModel.persistSelection(shell, moduleName, settings, tab)
  }

  function requestRefresh() {
    if (serviceAvailable) service.requestRefresh()
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(layout.contentWidth)
    contentHeight: panel.fittedContentHeight(layout.contentHeight)

    PanelShellLayout {
      id: layout
      edge: panel.barPos
      availableWidth: panel.availableCardWidth
      availableHeight: panel.availableCardHeight
      preferredWidth: Style.space(520)
      preferredHeight: Style.space(360)
    }

    // The host dispatcher remains part of the panel lifecycle contract. The
    // visible handler below owns Ctrl-modified tab semantics that it cannot expose.
    PanelKeyCatcher {
      visible: false
      blocked: true
    }

    Item {
      id: keyCatcher
      anchors.fill: parent
      focus: true
      Keys.priority: Keys.AfterItem
      Keys.onPressed: function(event) {
        if (tabState.handleKey(event.key, event.modifiers)) {
          event.accepted = true
        }
      }

      Flickable {
        id: contentFlick
        anchors.fill: parent
        contentWidth: width
        contentHeight: contentColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height

        Column {
          id: contentColumn
          width: contentFlick.width
          spacing: Style.spacing.panelGap

          PanelHero {
            width: parent.width
            title: "Opatchy"
            meta: root.panelView.summaryText
            detail: root.serviceAvailable ? "Source health" : "Unavailable"
            foreground: root.barForeground
            fontFamily: root.bar ? root.bar.fontFamily : Style.font.family

            iconComponent: Component {
              Text {
                text: "O"
                color: root.barForeground
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.display
              }
            }

            trailingControl: Component {
              PanelActionButton {
                iconText: root.panelView.refreshText === "Refreshing" ? "..." : "R"
                tooltipText: root.panelView.refreshText + " source scan"
                foreground: root.barForeground
                fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
                focusable: true
                enabled: root.serviceAvailable
                onClicked: root.requestRefresh()
              }
            }
          }

          SourceTabStrip {
            width: parent.width
            tabs: root.panelView.tabs
            selectedTab: tabState.selectedTab
            foreground: root.barForeground
            fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
            onSelected: function(tab) { tabState.select(tab, true) }
          }

          Text {
            width: parent.width
            visible: root.panelView.bannerText !== ""
            text: root.panelView.bannerText
            textFormat: Text.PlainText
            color: root.barForeground
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.Wrap
          }

          SourceContent {
            width: parent.width
            tab: tabState.selectedTab
            service: root.service
            snapshot: root.service ? root.service.lastSnapshot : null
            foreground: root.barForeground
            fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
          }

          Text {
            width: parent.width
            visible: root.panelView.failureText !== ""
            text: root.panelView.failureText
            textFormat: Text.PlainText
            color: root.barForeground
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.Wrap
          }

          Text {
            width: parent.width
            text: root.serviceAvailable
              ? tabState.selectedTab + ": " + root.panelView.tabs[TabModel.TAB_NAMES.indexOf(tabState.selectedTab)].count
                + " updates or findings. " + root.panelView.tabs[TabModel.TAB_NAMES.indexOf(tabState.selectedTab)].healthText
              : "Service unavailable. Source results cannot be shown."
            textFormat: Text.PlainText
            color: root.barForeground
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.pixelSize: Style.font.body
            wrapMode: Text.Wrap
          }

          Text {
            width: parent.width
            text: "Last scan attempt: " + root.panelView.lastAttemptText + ". Last successful result: " + root.panelView.lastSuccessText + "."
            textFormat: Text.PlainText
            color: root.barForeground
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.Wrap
          }
        }
      }

      PanelTabState {
        id: tabState
        onSelectionRequested: root.persistSelectedTab(tab)
        onCloseRequested: root.close()
      }
    }
  }

  onSettingsChanged: tabState.restore(setting("lastSelectedTab", "Security"), urgentSecurity)
  onUrgentSecurityChanged: tabState.restore(setting("lastSelectedTab", "Security"), urgentSecurity)
  Component.onCompleted: tabState.restore(setting("lastSelectedTab", "Security"), urgentSecurity)
}
