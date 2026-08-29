import QtQuick 2.15
import QtQuick.Window 2.15
import QtTest 1.3
import "../../qml/components"
import "../../qml/models/ProtocolValidator.js" as ProtocolValidator
import "../../qml/models/UpdateViewModel.js" as UpdateViewModel

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
      property var snapshot: null

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

  Component {
    id: stateComponent
    StarInteractionState { }
  }

  Component {
    id: retainedPermanentRowComponent
    Window {
      id: window
      visible: true
      width: 320
      height: 160
      property var service: ({ requests: [], setStar: function(request) { this.requests.push(request); return true } })
      StarInteractionState { id: stars; service: window.service }
      UpdateRow {
        id: updateRow
        width: parent.width
        expanded: true
        starState: stars
        row: ({ target: "omarchy:demo", id: "omarchy:demo", identity: "omarchy:omarchy:demo", label: "Demo", source: "omarchy", installed: "1.0", candidate: "2.0", watchText: "Watch: unavailable", watchMode: "permanent", watchable: false, temporaryArmed: false, healthText: "Evidence: Unavailable" })
      }
      property alias updateRow: updateRow
    }
  }

  function source(name, affectedSource, affectedStatus) {
    var status = name === affectedSource ? affectedStatus : "ok"
    var health = {
      source: name,
      status: status,
      provenance: status === "stale" ? "last_good" : "live",
      observedAt: "2026-08-26T00:00:00.000Z",
      freshUntil: "2026-08-26T00:05:00.000Z",
      cause: status === "stale" ? { code: "SOURCE_UNAVAILABLE", message: "Arch update evidence is last known." } : null
    }
    if (name === "flatpak") health.scopes = ["user", "system"].map(function(scope) {
      return { scope: scope, status: "ok", provenance: "live", observedAt: health.observedAt, freshUntil: health.freshUntil, cause: null }
    })
    return health
  }

  function snapshotFor(generationId, watchMode, affectedSource, affectedStatus) {
    var unavailable = affectedStatus !== "ok"
    var itemProvenance = unavailable ? "last_good" : "live"
    return ProtocolValidator.parseResponse(JSON.stringify({
      protocolVersion: 1,
      kind: "snapshot",
      generatedAt: "2026-08-26T00:00:00.000Z",
      generationId: generationId,
      payload: {
        scanState: unavailable ? "partial" : "complete",
        sources: ProtocolValidator.SOURCE_NAMES.map(function(name) { return source(name, affectedSource, affectedStatus) }),
        summary: { totalUpdates: 1, watchedUpdates: watchMode === "off" ? 0 : 1, securityFindings: 1, degradedSources: unavailable ? 1 : 0 },
        items: [{ id: affectedSource + ":demo", source: affectedSource, label: "Demo", installed: "1.0", candidate: "2.0", watchMode: watchMode, watchArmed: false, watchable: true, provenance: itemProvenance }],
        findings: [{
          itemId: "arch:demo",
          findings: [{ id: "AVG-1", itemId: "arch:demo", advisoryId: "AVG-1", cveIds: ["CVE-2026-0001"], severity: "high", fixedVersion: "2.0", installedVersion: "1.0", knownExploited: false, kevStatus: "unavailable", kevProvenance: null, provenance: "live", status: "Fixed", type: "security" }]
        }],
        notifications: [{ fingerprint: "watch:arch:demo", status: "delivered" }]
      }
    }))
  }

  function test_source_content_reconciles_real_same_target_buttons_and_retains_stale_watched_rows() {
    const initial = snapshotFor("generation-1", "off", "arch", "ok")
    verify(initial.ok)
    const view = sourceContentComponent.createObject(root, { snapshot: initial.value })
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

    const newer = snapshotFor("generation-2", "off", "arch", "ok")
    verify(newer.ok)
    view.snapshot = newer.value
    compare(view.first.view.mode, "off")
    compare(view.second.view.mode, "off")
    compare(view.other.view.mode, "off")

    const stale = snapshotFor("generation-3", "permanent", "arch", "stale")
    verify(stale.ok)
    view.snapshot = stale.value
    view.sourceContent.watchedOnly = true
    compare(view.sourceContent.displayedRows.length, 1)
    compare(view.sourceContent.displayedRows[0].target, "arch:demo")
    compare(view.sourceContent.displayedRows[0].healthText, "Evidence: Last known")
    view.destroy()
  }

  function test_unavailable_omarchy_row_does_not_start_a_watch_but_retained_permanent_can_clear() {
    const unavailable = snapshotFor("generation-1", "off", "omarchy", "error")
    verify(unavailable.ok)
    const state = stateComponent.createObject(root)
    const service = { requests: [], setStar: function(request) { this.requests.push(request); return true } }
    state.service = service

    const unavailableRow = UpdateViewModel.updateRows(unavailable.value, "Omarchy")[0]
    compare(unavailableRow.watchable, false)
    verify(!state.request("omarchy:demo", "off", unavailableRow.watchable))
    compare(service.requests.length, 0)

    const retained = snapshotFor("generation-2", "permanent", "omarchy", "error")
    verify(retained.ok)
    const retainedRow = UpdateViewModel.updateRows(retained.value, "Omarchy")[0]
    compare(retainedRow.watchable, false)
    verify(state.requestMode("omarchy:demo", "permanent", retainedRow.watchable, "off"))
    compare(service.requests.length, 1)
    compare(service.requests[0].mode, "off")
    state.destroy()
  }

  function test_stale_inventory_off_row_does_not_dispatch_a_watch_request() {
    const state = stateComponent.createObject(root)
    const service = { requests: [], setStar: function(request) { this.requests.push(request); return true } }
    state.service = service
    const stale = UpdateViewModel.inventoryState({
      generationId: "generation-old",
      payload: { source: "arch", total: 1, items: [{ id: "arch:demo", source: "arch", label: "Demo", installed: "1.0", candidate: "2.0", watchMode: "off", watchArmed: false, watchable: true }] }
    }, "arch", "generation-current")

    compare(stale.kind, "stale")
    compare(stale.rows[0].watchable, false)
    verify(!state.request(stale.rows[0].target, stale.rows[0].watchMode, stale.rows[0].watchable))
    compare(service.requests.length, 0)
    state.destroy()
  }

  function test_retained_permanent_row_exposes_only_its_clear_path() {
    const view = retainedPermanentRowComponent.createObject(root)
    verify(view.updateRow.watchTrigger.visible)
    verify(!view.updateRow.watchSelector.visible)
    view.updateRow.watchTrigger.clicked()
    compare(view.service.requests.length, 1)
    compare(view.service.requests[0].mode, "off")
    view.destroy()
  }
}
