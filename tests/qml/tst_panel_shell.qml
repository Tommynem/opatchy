import QtQuick 2.15
import QtQuick.Window 2.15
import QtTest 1.3
import "../../qml/components"

TestCase {
  id: root
  name: "OpatchyPanelShell"
  when: true

  property var serviceObject: null
  property var replacementService: null
  property var anchor: null
  property var panel: null

  Component {
    id: shellStateComponent
    PanelShellState { }
  }

  Component {
    id: layoutComponent

    PanelShellLayout { }
  }

  Component {
    id: inventoryStateComponent

    InventoryBrowseState { }
  }

  Component {
    id: inventoryPresentationComponent

    InventoryBrowsePresentation { }
  }

  Component {
    id: flatpakControlStackComponent

    BoundedControlStack {
      Item {
        objectName: "flatpak-user"
        width: parent.width
        height: 20
      }

      Item {
        objectName: "flatpak-system"
        width: parent.width
        height: 20
      }
    }
  }

  Component {
    id: browseControlStackComponent

    BoundedControlStack {
      Item {
        objectName: "browse"
        width: parent.width
        height: 20
      }
    }
  }

  Component {
    id: paginationControlStackComponent

    BoundedControlStack {
      Item {
        objectName: "previous"
        width: parent.width
        height: 20
      }

      Item {
        objectName: "page"
        width: parent.width
        height: 20
      }

      Item {
        objectName: "next"
        width: parent.width
        height: 20
      }
    }
  }

  Component {
    id: browseModeComponent

    BrowseModeState { }
  }

  Component {
    id: rowPresentationComponent

    UpdateRowPresentation { }
  }

  Component {
    id: inventoryServiceComponent

    QtObject {
      property var requests: []

      function requestInventory(request) {
        requests.push(request)
        return true
      }
    }
  }

  Component {
    id: panelServiceComponent

    QtObject {
      property var lastSnapshot: null
      property bool refreshing: false
      property var lastAttemptAt: null
      property var lastSuccessAt: null
      property string lastFailureKind: ""

      signal inventoryChanged(var source, var inventory, var operation)
      signal starResultChanged(var result, var operation)
      signal starFailed(var operation, string message)

      function requestRefresh() { }
    }
  }

  Component {
    id: fakePanelComponent
    QtObject {
      property bool opened: false
      property int openCalls: 0
      property int closeCalls: 0
      property int toggleCalls: 0

      function open() {
        openCalls += 1
        opened = true
      }

      function close() {
        closeCalls += 1
        opened = false
      }

      function toggle() {
        toggleCalls += 1
        opened = !opened
      }
    }
  }

  Component {
    id: emptyStatePanelComponent

    Window {
      id: host
      visible: true
      width: 640
      height: 480
      property alias state: state
      property alias bar: bar
      readonly property var widget: widgetLoader.item
      property var service: null
      property var manifest: ({
        "id": "io.github.tomge.opatchy",
        "__sourceDir": Qt.resolvedUrl("../..").toString()
      })

      QtObject {
        id: registry
        property var installedPlugins: ({ "io.github.tomge.opatchy": host.manifest })
      }

      QtObject {
        id: shell
        property var pluginRegistry: registry
        function serviceFor() { return host.service }
      }

      QtObject {
        id: bar
        property var shell: shell
        property color foreground: "black"
        property color urgent: "red"
        property string fontFamily: "Sans Serif"
        property real hostCardWidth: 607
        property real hostCardHeight: 360
      }

      PanelShellState {
        id: state
      }

      Loader {
        id: widgetLoader
        source: Qt.resolvedUrl("../../BarWidget.qml")
        onLoaded: {
          item.width = 32
          item.height = 32
          item.bar = bar
        }
      }
    }
  }

  Component {
    id: anchorComponent
    QtObject {
      property int focusCalls: 0

      function forceActiveFocus() {
        focusCalls += 1
      }
    }
  }

  function init() {
    serviceObject = panelServiceComponent.createObject(root)
    replacementService = Qt.createQmlObject("import QtQml; QtObject {}", root)
    anchor = anchorComponent.createObject(root)
    panel = fakePanelComponent.createObject(root)
  }

  function cleanup() {
    if (panel) panel.destroy()
    if (anchor) anchor.destroy()
    if (replacementService) replacementService.destroy()
    if (serviceObject) serviceObject.destroy()
  }

  function named(item, objectName) {
    if (!item) return null
    if (item.objectName === objectName) return item
    const children = item.children || []
    for (let index = 0; index < children.length; index += 1) {
      const result = named(children[index], objectName)
      if (result) return result
    }
    return null
  }

  function openProductionPanel(view) {
    tryVerify(function() { return view.widget !== null }, 1000)
    const button = named(view.widget, "opatchy-bar-icon")
    verify(button !== null, "bar widget must expose its real icon button")
    mouseClick(button)
    tryVerify(function() { return view.widget.panel !== null }, 1000)
    tryCompare(view.widget, "opened", true, 1000)
    return view.widget.panel
  }

  function hostSummarySnapshot() {
    const current = function(source) {
      return { source: source, status: "ok", provenance: "live" }
    }
    return {
      payload: {
        scanState: "complete",
        summary: { totalUpdates: 0, watchedUpdates: 0, securityFindings: 0, degradedSources: 0 },
        sources: [current("security"), current("cisa-kev"), current("omarchy"), current("arch"), current("aur"), current("flatpak"), current("mise")],
        items: [],
        findings: []
      }
    }
  }

  function test_header_summary_and_actions_are_bounded_at_host_and_narrow_widths() {
    serviceObject.lastSnapshot = hostSummarySnapshot()
    for (const width of [607, 320]) {
      const view = emptyStatePanelComponent.createObject(root, { "service": serviceObject })
      view.bar.hostCardWidth = width
      const panel = openProductionPanel(view)
      const hostPanel = named(panel, "opatchy-host-keyboard-panel")
      const content = named(hostPanel, "opatchy-host-content")
      const summary = named(panel, "opatchy-panel-hero-meta")
      verify(hostPanel !== null && content !== null && summary !== null, "host composition must expose the header geometry")
      tryVerify(function() { return summary.width > 0 }, 1000)
      if (width === 607)
        verify(!summary.truncated, "summary must receive its full rendered width at the active host width")
      for (const objectName of ["update-all", "refresh-source-scan", "settings-coming-later"]) {
        const control = named(panel, objectName)
        verify(control !== null, objectName + " must be instantiated by the production panel")
        const origin = control.mapToItem(content, 0, 0)
        verify(origin.x >= 0 && origin.y >= 0, objectName + " must start inside the panel")
        verify(origin.x + control.width <= content.width && origin.y + control.height <= content.height, objectName + " must stay within the panel")
      }
      view.destroy()
    }
  }

  function test_open_waits_for_the_one_lazy_panel_then_forwards_to_it() {
    const state = shellStateComponent.createObject(root, { "service": serviceObject })

    compare(state.statusText, "Opatchy")
    compare(state.loaderRequested, false)
    state.open()
    compare(state.loaderRequested, true)
    compare(state.pendingOperation, "open")
    compare(state.opened, false)

    state.panel = panel
    state.runPendingOperation(panel)
    compare(panel.openCalls, 1)
    compare(state.pendingOperation, "")
    compare(state.opened, true)
    compare(state.panel, panel)
    state.destroy()
  }

  function test_close_cancels_a_lazy_open_interrupted_by_a_shell_hide() {
    const state = shellStateComponent.createObject(root, { "service": serviceObject })

    state.open()
    compare(state.pendingOperation, "open")
    state.close()
    compare(state.pendingOperation, "")
    state.panel = panel
    state.runPendingOperation(panel)
    compare(panel.openCalls, 0)
    compare(state.opened, false)
    state.destroy()
  }

  function test_pending_lifecycle_operation_coalesces_after_panel_load_until_replay() {
    const state = shellStateComponent.createObject(root, { "service": serviceObject })

    state.open()
    state.panel = panel
    state.toggle()
    compare(state.pendingOperation, "toggle")
    compare(panel.openCalls, 0)
    compare(panel.toggleCalls, 0)

    state.runPendingOperation(panel)
    compare(state.pendingOperation, "")
    compare(panel.openCalls, 0)
    compare(panel.toggleCalls, 1)
    compare(state.opened, true)
    state.destroy()
  }

  function test_deferred_replay_ignores_a_replaced_panel() {
    const state = shellStateComponent.createObject(root, { "service": serviceObject })
    const replacement = fakePanelComponent.createObject(root)

    state.open()
    state.panel = panel
    state.panel = replacement
    state.runPendingOperation(panel)
    compare(state.pendingOperation, "open")
    compare(panel.openCalls, 0)
    compare(replacement.openCalls, 0)

    state.runPendingOperation(replacement)
    compare(state.pendingOperation, "")
    compare(replacement.openCalls, 1)
    replacement.destroy()
    state.destroy()
  }

  function test_repeated_lifecycle_operations_share_one_panel() {
    const state = shellStateComponent.createObject(root, {
      "service": serviceObject,
      "panel": panel
    })
    const identity = state.panel

    for (let cycle = 0; cycle < 100; cycle += 1) {
      state.open()
      state.close()
      state.toggle()
      state.toggle()
    }

    compare(state.panel, identity)
    compare(panel.openCalls, 100)
    compare(panel.closeCalls, 100)
    compare(panel.toggleCalls, 200)
    compare(state.opened, false)
    state.destroy()
  }

  function test_absent_service_and_loader_failure_remain_bounded() {
    const missingService = shellStateComponent.createObject(root)
    compare(missingService.statusText, "Service unavailable")
    missingService.open()
    compare(missingService.loaderRequested, true)
    missingService.loaderFailed = true
    compare(missingService.statusText, "Panel unavailable")
    missingService.open()
    compare(missingService.pendingOperation, "")
    missingService.destroy()
  }

  function test_click_without_a_validated_result_queues_and_opens_the_panel() {
    const view = emptyStatePanelComponent.createObject(root)
    verify(view !== null, "empty-state bar widget must load on the installed host button contract")
    tryVerify(function() { return view.widget !== null }, 1000)
    const button = view.widget.children.filter(function(child) {
      return child.objectName === "opatchy-bar-icon"
    })[0]
    verify(button !== null, "bar widget must expose its real icon button")

    mouseClick(button)
    tryVerify(function() { return view.widget.panel !== null }, 1000)
    tryCompare(view.widget, "opened", true, 1000)
    compare(view.widget.panel.statusText, "Service unavailable")
    view.destroy()
  }

  function test_lazy_loaded_pending_toggle_waits_for_deferred_replay() {
    const view = emptyStatePanelComponent.createObject(root, { "service": serviceObject })
    verify(view !== null, "host fixture must load")
    tryVerify(function() { return view.widget !== null }, 1000)

    view.widget.open()
    const loadedPanel = view.widget.panel
    verify(loadedPanel !== null, "the lazy loader must create a panel before deferred replay")
    compare(view.widget.opened, false)
    view.widget.toggle()
    compare(view.widget.opened, false, "the second request must remain queued until replay")
    tryCompare(view.widget, "opened", true, 1000)
    compare(view.widget.panel, loadedPanel, "deferred replay must retain the loaded panel")
    view.destroy()
  }

  function test_lazy_click_waits_for_host_card_geometry_before_opening() {
    const view = emptyStatePanelComponent.createObject(root, { "service": serviceObject })
    verify(view !== null, "host fixture must load")
    tryVerify(function() { return view.widget !== null }, 1000)
    compare(view.widget.panel, null, "the outer panel must remain lazy before the first request")

    const button = view.widget.children.filter(function(child) {
      return child.objectName === "opatchy-bar-icon"
    })[0]
    verify(button !== null, "bar widget must expose its real icon button")
    mouseClick(button)

    tryVerify(function() { return view.widget.panel !== null }, 1000)
    const panel = view.widget.panel
    compare(panel.bar, view.widget.bar)
    compare(panel.anchorItem, button)
    compare(panel.hostWidget, view.widget)
    verify(panel.settings !== null, "settings must be injected before opening")
    compare(panel.injectedService, serviceObject)

    const hostPanel = panel.children.filter(function(child) {
      return child.objectName === "opatchy-host-keyboard-panel"
    })[0]
    verify(hostPanel !== null, "the host keyboard panel facade must exist")
    tryVerify(function() { return hostPanel.geometryReady }, 1000)
    tryCompare(view.widget, "opened", true, 1000)

    const card = hostPanel.children.filter(function(child) {
      return child.objectName === "opatchy-host-card"
    })[0]
    const content = card.children.filter(function(child) {
      return child.objectName === "opatchy-host-content"
    })[0]
    verify(card.width > hostPanel.cardInset * 2, "opened card width must exceed an inset strip")
    verify(card.height > hostPanel.cardInset * 2, "opened card height must exceed an inset strip")
    verify(content.width > hostPanel.cardInset * 2, "content width must be materially positive")
    verify(content.height > hostPanel.cardInset * 2, "content height must be materially positive")

    const identity = panel
    mouseClick(button)
    tryCompare(view.widget, "opened", false, 1000)
    mouseClick(button)
    tryCompare(view.widget, "opened", true, 1000)
    compare(view.widget.panel, identity, "close/reopen must reuse the lazy panel")
    view.destroy()
  }

  function test_separate_host_modules_require_direct_panel_singleton_imports() {
    const view = emptyStatePanelComponent.createObject(root, { "service": serviceObject })
    verify(view !== null, "host fixture must load")
    tryVerify(function() { return view.widget !== null }, 1000)

    const button = view.widget.children.filter(function(child) {
      return child.objectName === "opatchy-bar-icon"
    })[0]
    verify(button !== null, "bar widget must expose its real icon button")
    mouseClick(button)

    tryVerify(function() { return view.widget.panel !== null }, 1000)
    tryCompare(view.widget, "opened", true, 1000)
    const hostPanel = view.widget.panel.children.filter(function(child) {
      return child.objectName === "opatchy-host-keyboard-panel"
    })[0]
    verify(hostPanel !== null, "the production panel must create the host keyboard panel")
    tryVerify(function() { return hostPanel.geometryReady }, 1000)
    verify(hostPanel.availableCardWidth > hostPanel.cardInset * 2, "preferred panel width must resolve through Style")
    verify(hostPanel.availableCardHeight > hostPanel.cardInset * 2, "preferred panel height must resolve through Style")
    verify(hostPanel.contentWidth > hostPanel.cardInset * 2, "fitted content width must remain positive")
    verify(hostPanel.contentHeight > hostPanel.cardInset * 2, "fitted content height must remain positive")
    view.destroy()
  }

  function test_service_replacement_and_close_return_focus_preserve_host_ownership() {
    const state = shellStateComponent.createObject(root, {
      "service": serviceObject,
      "anchorItem": anchor,
      "panel": panel
    })

    compare(state.service, serviceObject)
    state.service = replacementService
    compare(state.service, replacementService)
    state.close()
    compare(panel.closeCalls, 1)
    compare(anchor.focusCalls, 1)
    state.destroy()
  }

}
