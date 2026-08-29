import QtQuick 2.15
import qs.Commons

Item {
  id: root

  width: 760
  height: 560

  property int captureIndex: 0
  property string outputDirectory: outputDirectoryFromArguments()
  property var fixtureAnchor: fixtureAnchorItem
  property var fixtureBar: fixtureBarData
  property var fixtureService: fixtureServiceData
  property var fixtures: [
    { name: "clear", title: "Clear panel state", tab: "Security", kind: "clear" },
    { name: "dense-updates", title: "Dense update list state", tab: "System", kind: "dense" },
    { name: "conditional-security", title: "Conditional security watch state", tab: "Security", kind: "security" },
    { name: "stale-degraded", title: "Stale and degraded panel state", tab: "Security", kind: "stale" }
  ]
  property var currentFixture: fixtures[captureIndex]
  property var currentSnapshot: snapshotFor(currentFixture.kind)

  Rectangle {
    id: stage
    anchors.fill: parent
    color: "white"

    Column {
      anchors.fill: parent
      anchors.margins: Style.spacing.sm
      spacing: Style.spacing.sm

      Text {
        width: parent.width
        text: "ILLUSTRATIVE FIXTURE DATA - NOT A REAL HOST CAPTURE"
        textFormat: Text.PlainText
        color: Color.foreground
        font.family: Style.font.family
        font.pixelSize: Style.font.caption
        font.bold: true
        horizontalAlignment: Text.AlignHCenter
      }

      Text {
        width: parent.width
        text: root.currentFixture.title
        textFormat: Text.PlainText
        color: Color.foreground
        font.family: Style.font.family
        font.pixelSize: Style.font.bodySmall
        horizontalAlignment: Text.AlignHCenter
      }

      Item {
        id: panelStage
        width: parent.width
        height: parent.height - root.footerHeight

        Item {
          id: fixtureAnchorItem
          width: 1
          height: 1
        }

        QtObject {
          id: fixtureBarData
          property real hostCardWidth: panelStage.width
          property real hostCardHeight: panelStage.height
          property string fontFamily: Style.font.family
        }

        QtObject {
          id: fixtureServiceData
          property var lastSnapshot: root.currentSnapshot
          property bool refreshing: false
          property var lastAttemptAt: null
          property var lastSuccessAt: null
          property string lastFailureKind: ""
          property bool canUpdateAll: false
          property bool canOpenOmarchyUpdate: false
          property bool canOpenFlatpakUserUpdate: false
          property bool canOpenFlatpakSystemUpdate: false
          signal inventoryChanged(string source, var inventory, var operation)
          signal starResultChanged(var result, var operation)
          signal starFailed(var operation, string message)
          function requestRefresh() { return true }
          function requestUpdateAll() { return true }
          function openOmarchyUpdate() { return true }
          function openFlatpakUserUpdate() { return true }
          function openFlatpakSystemUpdate() { return true }
          function setStar(request) { return request && request.itemId === "arch:sample-library" }
        }

        Loader {
          id: panelLoader
          anchors.fill: parent
          active: false
        }
      }

      Text {
        id: footer
        width: parent.width
        text: "Fixture state: " + root.currentFixture.title + ". Invented bounded data only."
        textFormat: Text.PlainText
        color: Color.foreground
        font.family: Style.font.family
        font.pixelSize: Style.font.caption
        horizontalAlignment: Text.AlignHCenter
      }
    }
  }

  readonly property real footerHeight: Style.font.caption + Style.font.bodySmall + Style.font.caption + Style.spacing.sm * 4

  Timer {
    id: settleTimer
    interval: 180
    repeat: false
    onTriggered: root.prepareCapture()
  }

  Timer {
    id: captureTimer
    interval: 40
    repeat: false
    onTriggered: stage.grabToImage(function(result) {
      result.saveToFile(root.outputDirectory + "/" + root.currentFixture.name + ".png")
      root.captureIndex += 1
      root.startFixture()
    })
  }

  Component.onCompleted: startFixture()

  function startFixture() {
    if (captureIndex >= fixtures.length) {
      Qt.quit()
      return
    }
    panelLoader.active = false
    Qt.callLater(function() {
      panelLoader.setSource("../../Panel.qml", {
        "opened": true,
        "bar": root.fixtureBar,
        "anchorItem": root.fixtureAnchor,
        "injectedService": root.fixtureService,
        "settings": { "lastSelectedTab": root.currentFixture.tab, "reducedMotion": true }
      })
      settleTimer.start()
    })
  }

  function outputDirectoryFromArguments() {
    var prefix = "--output-directory="
    var values = Qt.application.arguments
    for (var index = 0; index < values.length; index += 1) {
      if (values[index].indexOf(prefix) === 0) return values[index].slice(prefix.length)
    }
    return "."
  }

  function prepareCapture() {
    if (currentFixture.kind === "dense") {
      var list = itemNamed(panelLoader.item, "opatchy-update-list")
      if (list) {
        list.forceLayout()
        list.contentY = Math.max(1, list.contentHeight - list.height)
      }
    }
    captureTimer.start()
  }

  function itemNamed(item, name) {
    if (!item) return null
    if (item.objectName === name) return item
    var children = item.children || []
    for (var index = 0; index < children.length; index += 1) {
      var match = itemNamed(children[index], name)
      if (match) return match
    }
    return null
  }

  function source(name, status) {
    return {
      source: name,
      status: status || "ok",
      provenance: status === "stale" ? "last_good" : "live",
      observedAt: "",
      freshUntil: "2099-01-01T00:00:00.000Z",
      cause: null
    }
  }

  function sources(archStatus, securityStatus) {
    return [
      source("security", securityStatus || "ok"),
      source("cisa-kev", "ok"),
      source("omarchy", "ok"),
      source("arch", archStatus || "ok"),
      source("aur", "ok"),
      source("flatpak", "ok"),
      source("mise", "ok")
    ]
  }

  function updateItem(index) {
    return {
      id: "arch:sample-package-" + index,
      source: "arch",
      label: "sample-package-" + index,
      installed: "1.0." + index,
      candidate: "1.1." + index,
      watchMode: "off",
      watchArmed: false,
      watchable: true
    }
  }

  function denseItems() {
    var values = []
    for (var index = 0; index < 150; index += 1) values.push(updateItem(index))
    return values
  }

  function securityGroup() {
    return [{
      itemId: "arch:sample-library",
      findings: [{
        id: "AVG-20260001",
        advisoryId: "AVG-20260001",
        itemId: "arch:sample-library",
        cveIds: ["CVE-2026-10001", "CVE-2026-10002"],
        severity: "high",
        fixedVersion: "9.9.9",
        installedVersion: "9.9.8",
        knownExploited: false,
        kevStatus: "not_listed",
        kevProvenance: "live",
        provenance: "live",
        status: "Fixed",
        type: "illustrative"
      }]
    }]
  }

  function snapshotFor(kind) {
    if (kind === "dense") {
      return { payload: { scanState: "complete", summary: { totalUpdates: 150, watchedUpdates: 0, securityFindings: 0 }, sources: sources("ok", "ok"), items: denseItems(), findings: [] } }
    }
    if (kind === "security") {
      return { payload: { scanState: "complete", summary: { totalUpdates: 1, watchedUpdates: 0, securityFindings: 1 }, sources: sources("ok", "ok"), items: [{ id: "arch:sample-library", source: "arch", label: "sample-library", installed: "9.9.8", candidate: "9.9.9", watchMode: "off", watchArmed: false, watchable: true }], findings: securityGroup() } }
    }
    if (kind === "stale") {
      return { payload: { scanState: "partial", summary: { totalUpdates: 1, watchedUpdates: 0, securityFindings: 0 }, sources: sources("stale", "stale"), items: [updateItem(0)], findings: [] } }
    }
    return { payload: { scanState: "complete", summary: { totalUpdates: 0, watchedUpdates: 0, securityFindings: 0 }, sources: sources("ok", "ok"), items: [], findings: [] } }
  }
}
