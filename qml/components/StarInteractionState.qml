import QtQuick
import "../models/StarViewModel.js" as StarViewModel

QtObject {
  id: root

  property var service: null
  property string snapshotGeneration: ""
  property bool notifyPermanent: true
  property bool pending: false
  property string pendingTarget: ""
  property string pendingMode: ""
  property string overrideTarget: ""
  property string overrideMode: ""
  property string overrideGeneration: ""
  property string errorText: ""

  signal reconcileRequested(string target)

  onSnapshotGenerationChanged: {
    if (overrideGeneration !== "" && snapshotGeneration !== overrideGeneration) clearOverride()
  }

  function modeFor(target, confirmedMode) {
    return target === overrideTarget ? overrideMode : confirmedMode
  }

  function stateFor(target, confirmedMode, watchable, temporaryArmed, lastKnown) {
    var view = StarViewModel.presentation(modeFor(target, confirmedMode), notifyPermanent, watchable, lastKnown)
    view.temporaryArmed = temporaryArmed === true
    view.pending = pending && pendingTarget === target
    if (view.pending) {
      view.enabled = false
      view.tooltip = "Updating watch preference. " + view.tooltip
      view.accessibleName = "Updating watch preference"
    } else if (pending) {
      view.enabled = false
    }
    return view
  }

  function request(target, confirmedMode, watchable) {
    if (pending || !service || typeof service.setStar !== "function") return false
    var view = StarViewModel.presentation(confirmedMode, notifyPermanent, watchable, false)
    if (!view.enabled || view.nextMode === null) return false
    if (service.setStar({ itemId: target, mode: view.nextMode }) !== true) return false
    pending = true
    pendingTarget = target
    pendingMode = view.nextMode
    errorText = ""
    return true
  }

  function acceptResult(result) {
    var payload = result && result.payload
    if (!pending || !payload || payload.itemId !== pendingTarget || payload.mode !== pendingMode) return
    overrideTarget = pendingTarget
    overrideMode = pendingMode
    overrideGeneration = snapshotGeneration
    pending = false
    pendingTarget = ""
    pendingMode = ""
    errorText = ""
    reconcileRequested(overrideTarget)
  }

  function acceptFailure(operation, message) {
    if (!pending || !operation || operation.kind !== "set-star" || operation.itemId !== pendingTarget || operation.mode !== pendingMode) return
    pending = false
    pendingTarget = ""
    pendingMode = ""
    errorText = typeof message === "string" ? message : "Watch preference could not be updated."
  }

  function clearOverride() {
    overrideTarget = ""
    overrideMode = ""
    overrideGeneration = ""
  }

}
