import QtQuick 2.15
import Quickshell

Item {
  id: root

  property int phase: 0
  property int failures: 0
  property var firstWidget: null
  property var secondWidget: null
  property var serviceObject: null
  property var currentService: null
  property var initialSettings: ({ "enableCisaKev": true })
  property var updatedSettings: ({ "enableCisaKev": false })
  property string sourceDir: Quickshell.env("OPATCHY_TEST_ROOT")
  property var manifest: ({
    "id": "io.github.tommynem.opatchy",
    "__sourceDir": sourceDir
  })

  QtObject {
    id: registry
    property var installedPlugins: ({ "io.github.tommynem.opatchy": root.manifest })
  }

  QtObject {
    id: shellHost
    property var pluginRegistry: registry
    property var serviceObject: root.currentService

    function serviceFor(pluginId) {
      return pluginId === root.manifest.id ? serviceObject : null
    }
  }

  QtObject {
    id: bar
    property var shell: shellHost
    property bool vertical: false
    property int barSize: 32
    property color barForeground: "white"
    property bool foregroundAnimationEnabled: false

    function showTooltip() {}
    function hideTooltip() {}
    function registerClickTarget() {}
    function unregisterClickTarget() {}
  }

  function check(condition, message) {
    if (condition) return
    failures += 1
    console.error("lifecycle-smoke: " + message)
  }

  function finish() {
    if (firstWidget) firstWidget.destroy()
    if (secondWidget) secondWidget.destroy()
    if (serviceObject) serviceObject.destroy()
    console.log("lifecycle-smoke: completed with " + failures + " failures")
    Qt.exit(failures === 0 ? 0 : 1)
  }

  Component.onCompleted: {
    check(sourceDir !== "", "OPATCHY_TEST_ROOT is required")
    const serviceComponent = Qt.createComponent("file://" + sourceDir + "/Service.qml")
    check(serviceComponent.status === Component.Ready, serviceComponent.errorString())
    if (failures > 0) {
      finish()
      return
    }
    serviceObject = serviceComponent.createObject(root, { "manifest": manifest, "shell": shellHost })
    check(serviceObject !== null, "service did not instantiate")
    if (failures > 0) {
      finish()
      return
    }
    currentService = serviceObject

    const widgetComponent = Qt.createComponent("file://" + sourceDir + "/BarWidget.qml")
    check(widgetComponent.status === Component.Ready, widgetComponent.errorString())
    if (failures > 0) {
      finish()
      return
    }
    firstWidget = widgetComponent.createObject(root, { "bar": bar, "settings": initialSettings })
    secondWidget = widgetComponent.createObject(root, { "bar": bar })
    check(firstWidget !== null && secondWidget !== null, "widgets did not instantiate")
    if (failures > 0) {
      finish()
      return
    }
    lifecycleTimer.start()
  }

  Timer {
    id: lifecycleTimer
    interval: 10
    repeat: false
    onTriggered: {
      if (root.phase === 0) {
        root.check(root.firstWidget.panel !== null && root.secondWidget.panel !== null, "panel facades did not load")
        root.check(root.firstWidget.service === root.serviceObject, "first widget did not resolve the shared service")
        root.check(root.secondWidget.panel.service === root.serviceObject, "second panel did not resolve the shared service")
        root.check(root.serviceObject.settings === root.initialSettings, "widget settings did not reach the shared service")
        root.firstWidget.settings = root.updatedSettings
        root.phase = 1
        lifecycleTimer.start()
        return
      }

      if (root.phase === 1) {
        root.check(root.serviceObject.settings === root.updatedSettings, "changed widget settings did not reach the shared service")
        root.currentService = null
        root.phase = 2
        lifecycleTimer.start()
        return
      }

      if (root.phase === 2) {
        root.check(!root.firstWidget.serviceAvailable, "absent service stayed available")
        root.check(root.firstWidget.statusText === "Service unavailable", "widget did not render unavailable state")
        root.check(root.secondWidget.panel.statusText === "Service unavailable", "panel did not render unavailable state")

        const serviceComponent = Qt.createComponent("file://" + root.sourceDir + "/Service.qml")
        const replacement = serviceComponent.createObject(root, { "manifest": root.manifest, "shell": shellHost })
        root.check(replacement !== null, "replacement service did not instantiate")
        root.currentService = replacement
        root.serviceObject.destroy()
        root.serviceObject = replacement
        root.phase = 3
        lifecycleTimer.start()
        return
      }

      root.check(root.firstWidget.service === root.serviceObject, "replacement service was not resolved")
      root.check(root.secondWidget.panel.service === root.serviceObject, "panel retained stale service")
      root.finish()
    }
  }
}
