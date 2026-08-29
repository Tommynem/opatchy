import QtQuick 2.15
import QtQuick.Window 2.15
import QtTest 1.3
import "../../qml/components"

TestCase {
  id: root
  name: "OpatchyInventoryBrowseCount"
  when: true

  Component {
    id: browseComponent

    Window {
      width: 320
      height: 240
      visible: true

      property alias browse: browse
      property alias inventoryState: inventoryState

      QtObject {
        id: inventoryState
        property string source: "arch"
        property string generationId: "generation-count"
        property string query: ""
        property int offset: 0
        property string statusText: ""
        property var inventory: response(rows("temporary", "off", "permanent"))
      }

      InventoryBrowseView {
        id: browse
        width: parent.width
        state: inventoryState
      }
    }
  }

  function item(index, watchMode) {
    return {
      id: "arch:item-" + index,
      source: "arch",
      label: "item-" + index,
      installed: "1.0",
      candidate: "2.0",
      watchMode: watchMode,
      watchArmed: false,
      watchable: true
    }
  }

  function rows(first, second, third) {
    return [item(1, first), item(2, second), item(3, third)]
  }

  function response(items, generationId) {
    return {
      generationId: generationId || "generation-count",
      payload: { source: "arch", total: 10, items: items }
    }
  }

  function test_watched_filter_reports_only_watched_items_on_loaded_page() {
    const view = browseComponent.createObject(root)

    compare(view.browse.view.rows.length, 3)
    compare(view.browse.displayedRows.length, 3)
    compare(view.browse.pageText(), "Showing 1-3 of 10")

    view.browse.watchedOnly = true
    wait(0)
    compare(view.browse.displayedRows.length, 2)
    compare(view.browse.pageText(), "2 watched items on this page.")

    view.inventoryState.inventory = response(rows("off", "off", "off"))
    wait(0)
    compare(view.browse.displayedRows.length, 0)
    compare(view.browse.pageText(), "No watched items on this page.")

    view.inventoryState.inventory = response(rows("temporary", "off", "off"))
    wait(0)
    compare(view.browse.displayedRows.length, 1)
    compare(view.browse.pageText(), "1 watched item on this page.")

    view.inventoryState.inventory = response(rows("temporary", "off", "permanent"))
    view.browse.watchedOnly = false
    wait(0)
    compare(view.browse.displayedRows.length, 3)
    compare(view.browse.pageText(), "Showing 1-3 of 10")
    view.destroy()
  }

  function test_watched_count_stays_page_local_for_stale_inventory() {
    const view = browseComponent.createObject(root)
    view.inventoryState.inventory = response(rows("temporary", "off", "permanent"), "generation-stale")
    view.browse.watchedOnly = true
    wait(0)

    compare(view.browse.view.kind, "stale")
    compare(view.browse.displayedRows.length, 2)
    compare(view.browse.pageText(), "2 watched items on this page.")
    view.destroy()
  }
}
