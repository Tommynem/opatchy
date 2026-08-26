import QtQml

QtObject {
  id: root

  property var service: null
  property var panel: null
  property var anchorItem: null
  property bool loaderRequested: false
  property bool loaderFailed: false
  property string pendingOperation: ""

  readonly property bool opened: panel ? panel.opened === true : false
  readonly property string statusText: loaderFailed
    ? "Panel unavailable"
    : (service ? "Opatchy" : "Service unavailable")

  onLoaderFailedChanged: {
    if (loaderFailed) pendingOperation = ""
  }

  function invoke(operation) {
    if (loaderFailed) return
    if (!panel) {
      loaderRequested = true
      pendingOperation = operation
      return
    }
    if (typeof panel[operation] === "function") panel[operation]()
  }

  function open() { invoke("open") }

  function close() {
    pendingOperation = ""
    if (panel && typeof panel.close === "function") panel.close()
    returnFocus()
  }

  function toggle() { invoke("toggle") }

  function runPendingOperation() {
    if (!panel || pendingOperation === "") return
    var operation = pendingOperation
    pendingOperation = ""
    if (typeof panel[operation] === "function") panel[operation]()
  }

  function returnFocus() {
    if (anchorItem && typeof anchorItem.forceActiveFocus === "function")
      anchorItem.forceActiveFocus()
  }
}
