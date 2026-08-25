import QtQuick 2.15
import QtTest 1.3

TestCase {
  id: root
  name: "OpatchyLifecycle"
  when: windowShown

  property var firstWidget: null
  property var secondWidget: null
  property var serviceObject: null
  property var currentService: null
  property var manifest: ({
    "id": "io.github.tomge.opatchy",
    "__sourceDir": Qt.resolvedUrl("../..").toString()
  })

  QtObject {
    id: registry
    property var installedPlugins: ({ "io.github.tomge.opatchy": root.manifest })
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

  function initTestCase() {
    const serviceComponent = Qt.createComponent(Qt.resolvedUrl("../../Service.qml"))
    compare(serviceComponent.status, Component.Ready, serviceComponent.errorString())
    serviceObject = serviceComponent.createObject(root, { "manifest": manifest, "shell": shellHost })
    verify(serviceObject !== null)
    currentService = serviceObject

    const widgetComponent = Qt.createComponent(Qt.resolvedUrl("../../BarWidget.qml"))
    compare(widgetComponent.status, Component.Ready, widgetComponent.errorString())
    firstWidget = widgetComponent.createObject(root, { "bar": bar })
    secondWidget = widgetComponent.createObject(root, { "bar": bar })
    verify(firstWidget !== null)
    verify(secondWidget !== null)
    tryVerify(function() { return firstWidget.panel !== null && secondWidget.panel !== null }, 1000)
  }

  function test_consumers_share_the_host_service() {
    compare(firstWidget.service, serviceObject)
    compare(secondWidget.service, serviceObject)
    compare(firstWidget.panel.service, serviceObject)
    compare(secondWidget.panel.service, serviceObject)
  }

  function test_absent_service_is_visible_and_never_constructed_by_a_facade() {
    currentService = null
    tryCompare(firstWidget, "serviceAvailable", false)
    tryCompare(secondWidget.panel, "serviceAvailable", false)
    compare(firstWidget.statusText, "Service unavailable")
    compare(secondWidget.panel.statusText, "Service unavailable")
  }

  function test_replacement_service_is_not_stale() {
    const serviceComponent = Qt.createComponent(Qt.resolvedUrl("../../Service.qml"))
    const replacement = serviceComponent.createObject(root, { "manifest": manifest, "shell": shellHost })
    verify(replacement !== null)
    currentService = replacement

    tryCompare(firstWidget, "service", replacement)
    compare(firstWidget.service === serviceObject, false)
    compare(secondWidget.panel.service, replacement)

    serviceObject.destroy()
    serviceObject = replacement
  }

  function cleanupTestCase() {
    if (firstWidget) firstWidget.destroy()
    if (secondWidget) secondWidget.destroy()
    if (serviceObject) serviceObject.destroy()
  }
}
