import QtQuick
import qs.Ui
import "qml/components"

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
      preferredWidth: Style.space(240)
      preferredHeight: statusText.implicitHeight
    }

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()

      Text {
        id: statusText
        anchors.centerIn: parent
        text: root.statusText
        color: root.barForeground
        font.family: root.bar ? root.bar.fontFamily : Style.font.family
        font.pixelSize: Style.font.body
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        maximumLineCount: 2
        elide: Text.ElideRight
      }
    }
  }
}
