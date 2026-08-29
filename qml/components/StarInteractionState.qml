import QtQuick
import "../models/StarViewModel.js" as StarViewModel

QtObject {
  id: root

  property var service: null
  property string snapshotGeneration: ""
  property bool notifyPermanent: true
  property bool reducedMotion: false
  readonly property int feedbackDuration: reducedMotion ? 0 : 100
  property bool pending: false
  property string pendingTarget: ""
  property string pendingMode: ""
  property var pendingCondition: null
  property string overrideTarget: ""
  property string overrideMode: ""
  property bool overrideArmed: false
  property string overrideGeneration: ""
  property string errorText: ""
  property string errorTarget: ""

  signal reconcileRequested(string target)
  signal feedbackRequested(string target)

  onSnapshotGenerationChanged: {
    if (overrideGeneration !== "" && snapshotGeneration !== overrideGeneration) clearOverride()
  }

  function modeFor(target, confirmedMode) {
    return target === overrideTarget ? overrideMode : confirmedMode
  }

  function stateFor(target, confirmedMode, watchable, temporaryArmed, lastKnown) {
    var effectiveArmed = target === overrideTarget ? overrideArmed : temporaryArmed
    var view = StarViewModel.presentation(modeFor(target, confirmedMode), notifyPermanent, watchable, lastKnown, effectiveArmed)
    view.pending = pending && pendingTarget === target
    if (view.pending) {
      view.enabled = false
      view.tooltip = "Updating watch preference. " + view.tooltip
      view.accessibleName = "Updating watch preference"
    } else if (pending) {
      view.enabled = false
    }
    view.errorText = target === errorTarget ? errorText : ""
    return view
  }

  function request(target, confirmedMode, watchable) {
    var view = StarViewModel.presentation(modeFor(target, confirmedMode), notifyPermanent, watchable, false)
    return requestMode(target, confirmedMode, watchable, view.nextMode)
  }

  function requestMode(target, confirmedMode, watchable, requestedMode, condition) {
    if (pending || !service || typeof service.setStar !== "function") return false
    var effectiveMode = modeFor(target, confirmedMode)
    var view = StarViewModel.presentation(effectiveMode, notifyPermanent, watchable, false)
    if (!view.enabled || requestedMode !== view.nextMode) return false
    var request = { itemId: target, mode: requestedMode }
    if (condition !== undefined && condition !== null) {
      if (requestedMode !== "temporary" || !validCondition(target, condition)) return false
      request.securityAdvisory = condition.securityAdvisory
      request.fixedVersion = condition.fixedVersion
      request.cveIds = condition.cveIds.slice()
    }
    if (service.setStar(request) !== true) return false
    pending = true
    pendingTarget = target
    pendingMode = requestedMode
    pendingCondition = condition === undefined || condition === null ? null : requestCondition(request)
    errorText = ""
    errorTarget = ""
    return true
  }

  function requestSecurityCondition(condition, confirmedMode, watchable) {
    if (!condition || typeof condition.itemId !== "string") return false
    return requestMode(condition.itemId, confirmedMode, watchable, "temporary", condition)
  }

  function acceptResult(result, operation) {
    var payload = result && result.payload
    if (!pending || !payload || !operation || !matchesPending(operation) || payload.itemId !== pendingTarget || payload.mode !== pendingMode) return
    overrideTarget = pendingTarget
    overrideMode = pendingMode
    overrideArmed = payload.watchArmed === true
    overrideGeneration = snapshotGeneration
    pending = false
    pendingTarget = ""
    pendingMode = ""
    pendingCondition = null
    errorText = ""
    errorTarget = ""
    reconcileRequested(overrideTarget)
    feedbackRequested(overrideTarget)
  }

  function acceptFailure(operation, message) {
    if (!pending || !operation || !matchesPending(operation)) return
    pending = false
    pendingTarget = ""
    pendingMode = ""
    pendingCondition = null
    errorText = typeof message === "string" ? message : "Watch preference could not be updated."
    errorTarget = operation.itemId
  }

  function clearOverride() {
    var target = overrideTarget
    overrideTarget = ""
    overrideMode = ""
    overrideGeneration = ""
    overrideArmed = false
    if (target !== "") feedbackRequested(target)
  }

  function matchesPending(operation) {
    if (operation.kind !== "set-star" || operation.itemId !== pendingTarget || operation.mode !== pendingMode) return false
    if (pendingCondition === null) return operation.securityAdvisory === undefined
    return operation.securityAdvisory === pendingCondition.securityAdvisory
      && operation.fixedVersion === pendingCondition.fixedVersion
      && equalCves(operation.cveIds, pendingCondition.cveIds)
  }

  function requestCondition(request) {
    return { securityAdvisory: request.securityAdvisory, fixedVersion: request.fixedVersion, cveIds: request.cveIds.slice() }
  }

  function validCondition(target, condition) {
    return /^arch:[A-Za-z0-9@_+][A-Za-z0-9@._+-]{0,127}$/.test(target)
      && typeof condition.securityAdvisory === "string" && /^AVG-[0-9]{1,120}$/.test(condition.securityAdvisory)
      && typeof condition.fixedVersion === "string" && condition.fixedVersion.length > 0 && condition.fixedVersion.length <= 256 && /^[\x20-\x7e]+$/.test(condition.fixedVersion)
      && stringList(condition.cveIds) && condition.cveIds.length > 0 && condition.cveIds.length <= 16
      && canonicalCves(condition.cveIds)
  }

  function equalCves(left, right) {
    if (!stringList(left) || !stringList(right) || left.length !== right.length) return false
    for (var index = 0; index < left.length; index += 1) {
      if (left[index] !== right[index]) return false
    }
    return true
  }

  function stringList(value) { return value !== null && typeof value === "object" && typeof value.length === "number" && Math.floor(value.length) === value.length }

  function canonicalCves(values) {
    for (var index = 0; index < values.length; index += 1) {
      if (!/^CVE-[0-9]{4}-[0-9]{4,19}$/.test(values[index])) return false
      for (var prior = 0; prior < index; prior += 1) {
        if (values[prior] === values[index]) return false
      }
    }
    return true
  }


}
