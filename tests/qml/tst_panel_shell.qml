import QtQuick 2.15
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
    id: anchorComponent

    QtObject {
      property int focusCalls: 0

      function forceActiveFocus() {
        focusCalls += 1
      }
    }
  }

  function init() {
    serviceObject = Qt.createQmlObject("import QtQml; QtObject {}", root)
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

  function test_open_waits_for_the_one_lazy_panel_then_forwards_to_it() {
    const state = shellStateComponent.createObject(root, { "service": serviceObject })

    compare(state.statusText, "Opatchy")
    compare(state.loaderRequested, false)
    state.open()
    compare(state.loaderRequested, true)
    compare(state.pendingOperation, "open")
    compare(state.opened, false)

    state.panel = panel
    state.runPendingOperation()
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
    state.runPendingOperation()
    compare(panel.openCalls, 0)
    compare(state.opened, false)
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

  function test_layout_is_bounded_for_each_bar_edge_and_narrow_screens() {
    const fixtures = [
      { "edge": "top", "width": 1280, "height": 720, "availableWidth": 1248, "availableHeight": 640 },
      { "edge": "bottom", "width": 1280, "height": 720, "availableWidth": 1248, "availableHeight": 640 },
      { "edge": "left", "width": 1280, "height": 720, "availableWidth": 1200, "availableHeight": 688 },
      { "edge": "right", "width": 1280, "height": 720, "availableWidth": 1200, "availableHeight": 688 },
      { "edge": "top", "width": 320, "height": 240, "availableWidth": 288, "availableHeight": 160 },
      { "edge": "left", "width": 240, "height": 320, "availableWidth": 160, "availableHeight": 288 }
    ]

    for (const fixture of fixtures) {
      const layout = layoutComponent.createObject(root, {
        "edge": fixture.edge,
        "screenWidth": fixture.width,
        "screenHeight": fixture.height,
        "barExtent": 40,
        "gap": 8,
        "margin": 16,
        "preferredWidth": 320,
        "preferredHeight": 96
      })

      verify(layout.contentWidth > 0, fixture.edge + " width must be positive")
      verify(layout.contentHeight > 0, fixture.edge + " height must be positive")
      compare(Math.round(layout.boundedAvailableWidth), fixture.availableWidth)
      compare(Math.round(layout.boundedAvailableHeight), fixture.availableHeight)
      verify(layout.contentWidth <= fixture.availableWidth, fixture.edge + " width must be constrained")
      verify(layout.contentHeight <= fixture.availableHeight, fixture.edge + " height must be constrained")
      layout.destroy()
    }
  }

  function test_cached_inventory_search_is_debounced_and_keeps_current_results_when_stale() {
    const service = inventoryServiceComponent.createObject(root)
    const state = inventoryStateComponent.createObject(root, {
      service: service,
      generationId: "generation-current"
    })

    state.open("arch")
    state.flush()
    compare(service.requests.length, 1)
    compare(service.requests[0].limit, 100)
    state.setQuery("STRASSE \u041a\u043b\u044e\u0447")
    state.flush()
    compare(service.requests[1].query, "STRASSE \u041a\u043b\u044e\u0447")
    state.acceptInventory("arch", {
      generationId: "generation-current",
      payload: { source: "arch", total: 1, items: [] }
    }, {
      argv: ["inventory", "--source", "arch", "--query", "STRASSE \u041a\u043b\u044e\u0447", "--limit", "100", "--offset", "0"]
    })
    compare(state.inventory.payload.source, "arch")
    state.acceptInventory("arch", {
      generationId: "generation-old",
      payload: { source: "arch", total: 0, items: [] }
    }, {
      argv: ["inventory", "--source", "arch", "--query", "STRASSE \u041a\u043b\u044e\u0447", "--limit", "100", "--offset", "0"]
    })
    compare(state.inventory.generationId, "generation-current")
    compare(state.statusText, "Cached inventory is stale; newer source data is required.")
    state.destroy()
    service.destroy()
  }
}
