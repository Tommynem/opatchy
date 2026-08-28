import QtQuick
import qs.Commons
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

  PanelShellLayout {
    id: layout
    edge: panel.barPos
    availableWidth: panel.availableCardWidth
    availableHeight: panel.availableCardHeight
    preferredWidth: Style.space(520)
    preferredHeight: Style.space(360)
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
            detail: ""
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
                objectName: "refresh-source-scan"
                iconText: "\uf0450"
                tooltipText: root.panelView.refreshText + " source scan"
                foreground: root.barForeground
                fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
                focusable: true
                enabled: root.serviceAvailable
                onClicked: root.requestRefresh()
              }
            }
          }

          PanelProblemSummary {
            width: parent.width
            title: root.panelView.problemTitle
            detail: root.panelView.problemDetail
            evidence: root.panelView.failureText !== ""
              ? root.panelView.failureText
              : "Last attempt " + root.panelView.lastAttemptText + "; last validated result " + root.panelView.lastSuccessText + "."
            glyph: root.panelView.problemGlyph
            foreground: root.barForeground
            fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
          }

          SourceTabStrip {
            width: parent.width
            tabs: root.panelView.tabs
            selectedTab: tabState.selectedTab
            foreground: root.barForeground
            fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
            onSelected: function(tab) { tabState.select(tab, true) }
          }

          SourceContent {
            width: parent.width
            tab: tabState.selectedTab
            service: root.service
            snapshot: root.service ? root.service.lastSnapshot : null
            notifyPermanent: setting("notifyPermanent", true) === true
            reducedMotion: setting("reducedMotion", false) === true
            foreground: root.barForeground
            fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
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
