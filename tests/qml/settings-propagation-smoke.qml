import QtQuick
import Quickshell

ShellRoot {
  id: root

  property var service: null
  property var initialSettings: ({ "enableCisaKev": true })
  property var updatedSettings: ({ "enableCisaKev": false })
  property var manifest: ({
    "id": "io.github.tommynem.opatchy",
    "__sourceDir": Quickshell.env("OPATCHY_TEST_ROOT")
  })

  QtObject {
    id: registry
    property var installedPlugins: ({ "io.github.tommynem.opatchy": root.manifest })
  }

  QtObject {
    id: shellHost
    property var pluginRegistry: registry
    property var serviceObject: root.service

    function serviceFor(pluginId) {
      return pluginId === root.manifest.id ? serviceObject : null
    }
  }

  QtObject {
    id: bar
    property var shell: shellHost
    property color foreground: "white"
    property color urgent: "red"
  }

  function fail(message) {
    console.error("settings-propagation-smoke: " + message)
    Qt.exit(1)
  }

  Component.onCompleted: {
    const serviceComponent = Qt.createComponent("file://" + manifest.__sourceDir + "/Service.qml")
    service = serviceComponent.createObject(root, { "manifest": manifest, "shell": shellHost })
    if (service === null) {
      fail("service did not instantiate: " + serviceComponent.errorString())
      return
    }
    const widgetComponent = Qt.createComponent("file://" + manifest.__sourceDir + "/BarWidget.qml")
    const widget = widgetComponent.createObject(root, { "bar": bar })
    if (widget === null) {
      fail("widget did not instantiate: " + widgetComponent.errorString())
      return
    }
    widget.settings = initialSettings
    verifyTimer.widget = widget
    Qt.callLater(function() { verifyTimer.start() })
  }

  Timer {
    id: verifyTimer
    property var widget: null
    property bool updated: false
    interval: 0
    repeat: false
    onTriggered: {
      if (!updated) {
        if (shellHost.serviceFor(manifest.id) !== service) {
          fail("host did not resolve the shared service")
          return
        }
        if (widget.service !== service) {
          fail("widget did not resolve the shared service")
          return
        }
        if (widget.settings !== initialSettings) {
          fail("host did not inject the initial widget settings")
          return
        }
        if (service.settings !== initialSettings) {
          fail("initial widget settings did not reach the shared service")
          return
        }
        widget.settings = updatedSettings
        updated = true
        start()
        return
      }
      if (service.settings !== updatedSettings) {
        fail("updated widget settings did not reach the shared service")
        return
      }
      console.log("settings-propagation-smoke: shared settings updated")
      widget.destroy()
      service.destroy()
      Qt.exit(0)
    }
  }
}
