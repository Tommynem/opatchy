import QtQuick 2.15
import QtTest 1.3

TestCase {
  id: root
  name: "OpatchyLifecycle"
  when: true

  property var firstConsumer: null
  property var secondConsumer: null
  property var missingCapabilityConsumer: null
  property var serviceObject: null
  property var currentService: null
  property var manifest: ({
    "id": "io.github.tommynem.opatchy",
    "__sourceDir": Qt.resolvedUrl("../..").toString()
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
    id: shellWithoutServiceFor
    property var pluginRegistry: registry
  }

  QtObject {
    id: initialService
  }

  QtObject {
    id: replacementService
  }

  function initTestCase() {
    serviceObject = initialService
    currentService = serviceObject

    const lifecycleComponent = Qt.createComponent(Qt.resolvedUrl("../../LifecycleState.qml"))
    compare(lifecycleComponent.status, Component.Ready, lifecycleComponent.errorString())
    firstConsumer = lifecycleComponent.createObject(root, { "shell": shellHost, "manifest": manifest })
    secondConsumer = lifecycleComponent.createObject(root, { "shell": shellHost, "manifest": manifest })
    missingCapabilityConsumer = lifecycleComponent.createObject(root, {
      "shell": shellWithoutServiceFor,
      "manifest": manifest
    })
    verify(firstConsumer !== null)
    verify(secondConsumer !== null)
    verify(missingCapabilityConsumer !== null)
  }

  function init() {
    currentService = serviceObject
  }

  function test_consumers_share_the_host_service() {
    compare(firstConsumer.service, serviceObject)
    compare(secondConsumer.service, serviceObject)
  }

  function test_absent_service_is_visible_and_never_constructed_by_a_facade() {
    currentService = null
    tryCompare(firstConsumer, "serviceAvailable", false)
    tryCompare(secondConsumer, "serviceAvailable", false)
    compare(firstConsumer.statusText, "Service unavailable")
    compare(secondConsumer.statusText, "Service unavailable")
  }

  function test_missing_service_capability_is_visible() {
    compare(missingCapabilityConsumer.serviceAvailable, false)
    compare(missingCapabilityConsumer.statusText, "Service unavailable")
  }

  function test_replacement_service_is_not_stale() {
    currentService = replacementService

    tryCompare(firstConsumer, "service", replacementService)
    compare(firstConsumer.service === serviceObject, false)
    compare(secondConsumer.service, replacementService)
  }

  function cleanupTestCase() {
    if (firstConsumer) firstConsumer.destroy()
    if (secondConsumer) secondConsumer.destroy()
    if (missingCapabilityConsumer) missingCapabilityConsumer.destroy()
  }
}
