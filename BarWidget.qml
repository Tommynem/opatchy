import QtQuick
import qs.Commons
import qs.Ui
import "qml/components"

BarWidget {
  id: root
  moduleName: "io.github.tommynem.opatchy"

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
  readonly property var status: statusPresentation.status

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

  BarStatusPresentation {
    id: statusPresentation
    snapshot: root.service ? root.service.lastSnapshot : null
    refreshing: root.service ? root.service.refreshing === true : false
    serviceAvailable: root.serviceAvailable
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

  function synchronizeServiceSettings() {
    const sharedService = shell && manifest && typeof shell.serviceFor === "function"
      ? shell.serviceFor(manifest.id)
      : null
    if (sharedService && "settings" in sharedService)
      sharedService.settings = root.settings
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

  onBarChanged: {
    synchronizeServiceSettings()
    injectPanel()
  }
  onSettingsChanged: {
    synchronizeServiceSettings()
    injectPanel()
  }
  onServiceChanged: {
    synchronizeServiceSettings()
    injectPanel()
  }
  Component.onCompleted: Qt.callLater(synchronizeServiceSettings)
  onPanelChanged: {
    injectPanel()
  }

  Loader {
    id: panelLoader
    active: panelState.loaderRequested && root.sourceDir !== ""
    source: root.sourceDir === "" ? "" : root.sourceDir + "/Panel.qml"
    visible: false
    onLoaded: {
      const loadedPanel = panel
      root.injectPanel()
      Qt.callLater(function() {
        if (panel !== loadedPanel || panelState.panel !== loadedPanel) return
        root.injectPanel()
        Qt.callLater(function() {
          if (panel === loadedPanel && panelState.panel === loadedPanel)
            panelState.runPendingOperation(loadedPanel)
        })
      })
    }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.status.label
    iconComponent: statusIconComponent
    tooltipText: root.status.tooltip
    foreground: root.bar ? root.bar.foreground : Color.foreground
    activeColor: root.bar ? root.bar.urgent : Color.urgent
    active: root.status.active
    dimmed: root.status.kind === "clear"
    onPressed: function() { root.togglePanel() }
  }

  Component {
    id: statusIconComponent
    BarStatusIcon {
      icon: root.status.icon
      badge: root.status.badge
      stale: root.status.stale
      refreshing: root.status.spinner
      reducedMotion: root.settings && root.settings.reducedMotion === true
      foreground: root.bar ? root.bar.foreground : Color.foreground
      urgent: root.bar ? root.bar.urgent : Color.urgent
      fontFamily: button.fontFamily
      fontSize: button.fontSize
    }
  }
}
