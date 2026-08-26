import QtQuick
import qs.Ui
import "qml/components"

BarWidget {
  id: root
  moduleName: "io.github.tomge.opatchy"

  readonly property var shell: bar ? bar.shell : null
  readonly property var manifest: shell && shell.pluginRegistry
    ? shell.pluginRegistry.installedPlugins[moduleName] || null
    : null
  readonly property string sourceDir: manifest && typeof manifest.__sourceDir === "string"
    ? manifest.__sourceDir
    : ""
  readonly property var service: lifecycleState.service
  readonly property bool serviceAvailable: lifecycleState.serviceAvailable
  readonly property var panel: panelLoader.item
  readonly property string statusText: panelState.statusText

  LifecycleState {
    id: lifecycleState
    shell: root.shell
    manifest: root.manifest
  }

  PanelShellState {
    id: panelState
    service: root.service
    panel: root.panel
    anchorItem: button
    loaderFailed: panelLoader.status === Loader.Error
  }

  function injectPanel() {
    if (!panel) return
    panel.bar = root.bar
    panel.settings = root.settings
    panel.shell = root.shell
    panel.manifest = root.manifest
    panel.anchorItem = button
    panel.hostWidget = root
    panel.injectedService = root.service
  }

  function open() {
    panelState.open()
  }

  function close() {
    panelState.close()
  }

  function toggle() { panelState.toggle() }

  function togglePanel() { toggle() }

  readonly property bool opened: panel ? panel.opened === true : false
  readonly property bool popoutSwitchClosing: panel
    ? panel.popoutSwitchClosing === true
    : false

  function closeForPopoutSwitch() {
    if (panel && typeof panel.closeForPopoutSwitch === "function")
      panel.closeForPopoutSwitch()
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()
  onServiceChanged: injectPanel()
  onPanelChanged: {
    injectPanel()
    panelState.runPendingOperation()
  }

  Loader {
    id: panelLoader
    active: panelState.loaderRequested && root.sourceDir !== ""
    source: root.sourceDir === "" ? "" : root.sourceDir + "/Panel.qml"
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(function() {
        root.injectPanel()
        panelState.runPendingOperation()
      })
    }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.vertical ? "O" : root.statusText
    tooltipText: root.serviceAvailable
      ? "Open Opatchy"
      : "Opatchy service unavailable"
    onPressed: function() { root.togglePanel() }
  }
}
