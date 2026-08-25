import QtQuick
import qs.Ui

Panel {
  id: root
  moduleName: "io.github.tomge.opatchy"
  manageIpc: false

  property var shell: null
  property var manifest: null
  property var anchorItem: null
  property var hostWidget: null
  readonly property var service: shell && manifest ? shell.serviceFor(manifest.id) : null
  readonly property bool serviceAvailable: service !== null
  readonly property string statusText: serviceAvailable ? "Opatchy" : "Service unavailable"

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.hostWidget || root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(240))
    contentHeight: panel.fittedContentHeight(statusText.implicitHeight + Style.space(16))

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
      }
    }
  }
}
