import QtQuick
import qs.Ui

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
  readonly property string statusText: lifecycleState.statusText
  readonly property var panel: panelLoader.item

  LifecycleState {
    id: lifecycleState
    shell: root.shell
    manifest: root.manifest
  }

  function injectPanel() {
    if (!panel) return
    panel.bar = root.bar
    panel.shell = root.shell
    panel.manifest = root.manifest
    panel.anchorItem = button
    panel.hostWidget = root
  }

  function open() {
    if (panel) panel.open()
  }

  function close() {
    if (panel) panel.close()
  }

  function togglePanel() {
    if (panel) panel.toggle()
  }

  readonly property bool opened: panel ? panel.opened === true : false

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onBarChanged: injectPanel()

  Loader {
    id: panelLoader
    active: root.sourceDir !== ""
    source: root.sourceDir === "" ? "" : root.sourceDir + "/Panel.qml"
    visible: false
    onLoaded: root.injectPanel()
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.statusText
    tooltipText: root.serviceAvailable
      ? "Open Opatchy"
      : "Opatchy service unavailable"
    onPressed: function() { root.togglePanel() }
  }
}
