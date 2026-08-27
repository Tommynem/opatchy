import QtQuick 2.15
import QtTest 1.3
import "../../qml/components"

TestCase {
  id: root
  name: "OpatchyPanelLayout"
  when: true

  Component { id: layoutComponent; PanelShellLayout { } }
  Component { id: inventoryStateComponent; InventoryBrowseState { } }
  Component { id: inventoryPresentationComponent; InventoryBrowsePresentation { } }
  Component { id: browseModeComponent; BrowseModeState { } }
  Component { id: rowPresentationComponent; UpdateRowPresentation { } }
  Component {
    id: inventoryServiceComponent
    QtObject {
      property var requests: []
      function requestInventory(request) { requests.push(request); return true }
    }
  }
  Component {
    id: controlStackComponent
    BoundedControlStack {
      Item { objectName: "first"; width: parent.width; height: 20 }
      Item { objectName: "second"; width: parent.width; height: 20 }
      Item { objectName: "third"; width: parent.width; height: 20 }
    }
  }

  function test_layout_is_bounded_for_each_bar_edge_and_narrow_screens() {
    const fixtures = [
      { edge: "top", width: 1280, height: 720, availableWidth: 1248, availableHeight: 640 },
      { edge: "bottom", width: 1280, height: 720, availableWidth: 1248, availableHeight: 640 },
      { edge: "left", width: 1280, height: 720, availableWidth: 1200, availableHeight: 688 },
      { edge: "right", width: 1280, height: 720, availableWidth: 1200, availableHeight: 688 },
      { edge: "top", width: 320, height: 240, availableWidth: 288, availableHeight: 160 },
      { edge: "left", width: 240, height: 320, availableWidth: 160, availableHeight: 288 }
    ]
    for (const fixture of fixtures) {
      const layout = layoutComponent.createObject(root, {
        edge: fixture.edge,
        screenWidth: fixture.width,
        screenHeight: fixture.height,
        barExtent: 40,
        gap: 8,
        margin: 16,
        preferredWidth: 320,
        preferredHeight: 96
      })
      compare(Math.round(layout.boundedAvailableWidth), fixture.availableWidth)
      compare(Math.round(layout.boundedAvailableHeight), fixture.availableHeight)
      verify(layout.contentWidth > 0 && layout.contentWidth <= fixture.availableWidth)
      verify(layout.contentHeight > 0 && layout.contentHeight <= fixture.availableHeight)
      layout.destroy()
    }
  }

  function test_cached_inventory_search_is_debounced_and_keeps_current_results_when_stale() {
    const service = inventoryServiceComponent.createObject(root)
    const state = inventoryStateComponent.createObject(root, { service: service, generationId: "generation-current" })
    const operation = { argv: ["inventory", "--source", "arch", "--query", "STRASSE \u041a\u043b\u044e\u0447", "--limit", "100", "--offset", "0"] }
    state.open("arch")
    state.flush()
    compare(service.requests.length, 1)
    state.setQuery("STRASSE \u041a\u043b\u044e\u0447")
    state.flush()
    state.acceptInventory("arch", { generationId: "generation-current", payload: { source: "arch", total: 1, items: [] } }, operation)
    state.acceptInventory("arch", { generationId: "generation-old", payload: { source: "arch", total: 0, items: [] } }, operation)
    compare(state.inventory.generationId, "generation-current")
    state.destroy()
    service.destroy()
  }

  function test_accepted_inventory_remains_visible_as_last_known_until_current_response_replaces_it() {
    const service = inventoryServiceComponent.createObject(root)
    const state = inventoryStateComponent.createObject(root, { service: service, generationId: "generation-a" })
    const presentation = inventoryPresentationComponent.createObject(root, { state: state })
    const operation = { argv: ["inventory", "--source", "arch", "--query", "", "--limit", "100", "--offset", "0"] }
    const retained = { id: "arch:retained", source: "arch", label: "retained", installed: "1.0", candidate: "1.1", watchable: true, watchArmed: false, watchMode: "off" }
    state.open("arch")
    state.flush()
    state.acceptInventory("arch", { generationId: "generation-a", payload: { source: "arch", total: 1, items: [retained] } }, operation)
    state.generationId = "generation-b"
    compare(presentation.view.kind, "stale")
    compare(presentation.view.rows[0].id, "arch:retained")
    state.acceptInventory("arch", { generationId: "generation-b", payload: { source: "arch", total: 1, items: [Object.assign({}, retained, { id: "arch:replacement" })] } }, operation)
    compare(presentation.view.rows[0].id, "arch:replacement")
    presentation.destroy()
    state.destroy()
    service.destroy()
  }

  function test_control_stacks_and_browse_state_stay_bounded_when_narrow() {
    for (const width of [160, 520]) {
      const stack = controlStackComponent.createObject(root, { width: width })
      for (const control of stack.controls) verify(control.x >= 0 && control.x + control.width <= stack.width)
      stack.destroy()
    }
    const state = browseModeComponent.createObject(root, { tab: "System", browsing: true })
    state.tab = "AUR"
    compare(state.browsing, false)
    state.destroy()
  }

  function test_update_row_presentation_keeps_hostile_model_text_plain_and_bounded() {
    const nullCharacter = String.fromCharCode(0)
    const hostile = "$(touch /tmp/opatchy-injection-sentinel)\n\u202e\u4f60\u597d \u0645\u0631\u062d\u0628\u0627" + nullCharacter + "x".repeat(2000)
    const presentation = rowPresentationComponent.createObject(root, { row: { id: "arch:hostile", source: "arch", label: hostile, installed: hostile, candidate: hostile, watchable: true, watchMode: hostile } })
    verify(presentation.label.indexOf("\n") === -1 && presentation.label.indexOf(nullCharacter) === -1)
    verify(presentation.label.length <= 256 && presentation.detailsText.indexOf("\n") === -1)
    verify(presentation.detailsText.indexOf("opatchy-injection-sentinel") !== -1)
    presentation.destroy()
  }
}
