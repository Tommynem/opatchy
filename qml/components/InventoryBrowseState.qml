import QtQuick
import "../models/UpdateViewModel.js" as UpdateViewModel

QtObject {
  id: root

  property var service: null
  property string generationId: ""
  property string source: ""
  property string query: ""
  property int offset: 0
  property var inventory: null
  property var request: null
  property bool loading: false
  property string statusText: ""

  function open(nextSource) {
    source = nextSource
    query = ""
    offset = 0
    inventory = null
    statusText = "Loading cached inventory."
    queueRequest()
  }

  function setQuery(value) {
    query = UpdateViewModel.boundedQuery(value)
    offset = 0
    queueRequest()
  }

  function nextPage(total) {
    if (offset + UpdateViewModel.PAGE_SIZE >= total) return
    offset += UpdateViewModel.PAGE_SIZE
    queueRequest()
  }

  function previousPage() {
    if (offset === 0) return
    offset = Math.max(0, offset - UpdateViewModel.PAGE_SIZE)
    queueRequest()
  }

  function queueRequest() {
    if (source === "") return
    debounce.restart()
  }

  function flush() {
    debounce.stop()
    sendRequest()
  }

  function sendRequest() {
    var next = UpdateViewModel.inventoryRequestForSource(source, query, offset)
    if (next === null || !service || typeof service.requestInventory !== "function") {
      loading = false
      statusText = "Cached inventory is unavailable."
      return
    }
    request = next
    loading = service.requestInventory(next) === true
    statusText = loading ? "Loading cached inventory." : "Cached inventory is unavailable."
  }

  function acceptInventory(changedSource, response, operation) {
    if (!matchesRequest(changedSource, operation)) return
    loading = false
    var view = UpdateViewModel.inventoryState(response, source, generationId)
    if (view.kind !== "ready") {
      var displayed = UpdateViewModel.inventoryState(inventory, source, generationId)
      statusText = displayed.kind === "empty" ? view.summaryText : (displayed.kind === "ready" ? "" : displayed.summaryText)
      return
    }
    inventory = response
    statusText = ""
  }

  function matchesRequest(changedSource, operation) {
    if (!request || changedSource !== request.source || !operation || !Array.isArray(operation.argv)) return false
    var argv = operation.argv
    return argv.length === 9 && argv[0] === "inventory" && argv[1] === "--source" && argv[2] === request.source
      && argv[3] === "--query" && argv[4] === request.query && argv[5] === "--limit" && argv[6] === "100"
      && argv[7] === "--offset" && argv[8] === String(request.offset)
  }

  property Timer debounce: Timer {
    interval: 200
    repeat: false
    onTriggered: root.sendRequest()
  }
}
