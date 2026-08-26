import QtQuick 2.15
import QtQuick.Window 2.15
import QtTest 1.3
import "../../qml/components"

TestCase {
  id: root
  name: "OpatchyStarSourceContent"
  when: true

  Component {
    id: sourceContentComponent

    Window {
      id: window
      visible: true
      width: 160
      height: 192
      property var snapshot: root.snapshotFor("generation-1", "off", "ok")

      QtObject {
        id: service
        property var requests: []
        signal inventoryChanged(string source, var inventory, var operation)
        signal starResultChanged(var result, var operation)
        signal starFailed(var operation, string message)

        function setStar(request) {
          requests.push(request)
          return true
        }
      }

      SourceContent {
        id: sourceContent
        width: parent.width
        tab: "System"
        service: service
        snapshot: window.snapshot
      }

      StarButton {
        id: first
        width: parent.width
        height: 48
        y: 0
        z: 1
        starState: sourceContent.starState
        target: "arch:demo"
        confirmedMode: "off"
        watchable: true
      }

      StarButton {
        id: second
        width: parent.width
        height: 48
        y: 48
        z: 1
        starState: sourceContent.starState
        target: "arch:demo"
        confirmedMode: "off"
        watchable: true
      }

      StarButton {
        id: other
        width: parent.width
        height: 48
        y: 96
        z: 1
        starState: sourceContent.starState
        target: "arch:other"
        confirmedMode: "off"
        watchable: true
      }

      property alias sourceContent: sourceContent
      property alias service: service
      property alias first: first
      property alias second: second
      property alias other: other
    }
  }

  function snapshotFor(generationId, watchMode, sourceStatus) {
    return {
      generationId: generationId,
      payload: {
        sources: [{
          source: "arch",
          status: sourceStatus,
          provenance: sourceStatus === "stale" ? "last_good" : "live"
        }],
        items: [{
          id: "arch:demo",
          source: "arch",
          label: "Demo",
          installed: "1.0",
          candidate: "2.0",
          watchMode: watchMode,
          watchArmed: false,
          watchable: true
        }]
      }
    }
  }

  function test_source_content_reconciles_real_same_target_buttons_and_retains_stale_watched_rows() {
    const view = sourceContentComponent.createObject(root)
    verify(view.sourceContent.starState !== null)
    compare(view.first.starState, view.sourceContent.starState)
    compare(view.second.starState, view.sourceContent.starState)
    compare(view.other.starState, view.sourceContent.starState)
    compare(view.first.view.mode, "off")
    compare(view.second.view.mode, "off")
    compare(view.other.view.mode, "off")

    verify(view.sourceContent.starState.request("arch:demo", "off", true))
    compare(view.service.requests.length, 1)
    compare(view.service.requests[0].itemId, "arch:demo")
    compare(view.service.requests[0].mode, "temporary")

    view.service.starResultChanged({ payload: { itemId: "arch:demo", mode: "temporary", watchArmed: true } }, {
      kind: "set-star", itemId: "arch:demo", mode: "temporary"
    })
    compare(view.first.view.mode, "temporary")
    compare(view.second.view.mode, "temporary")
    compare(view.other.view.mode, "off")

    view.snapshot = snapshotFor("generation-2", "off", "ok")
    compare(view.first.view.mode, "off")
    compare(view.second.view.mode, "off")
    compare(view.other.view.mode, "off")

    view.snapshot = snapshotFor("generation-3", "permanent", "stale")
    view.sourceContent.watchedOnly = true
    compare(view.sourceContent.displayedRows.length, 1)
    compare(view.sourceContent.displayedRows[0].target, "arch:demo")
    compare(view.sourceContent.displayedRows[0].healthText, "Source health: Last known")
    view.destroy()
  }
}
