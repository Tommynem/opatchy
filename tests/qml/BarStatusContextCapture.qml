import QtQuick 2.15
import QtQml 2.15
import "../../qml/components"

Item {
  id: root
  width: 680; height: 220
  property int captureIndex: 0
  property string outputDirectory: ".omo/evidence/task-24-opatchy/visual-qa/context"
  property string productionIconFont: "monospace"
  property var fixtures: [
    { name: "security-stale-dark-horizontal", state: "security", dark: true, vertical: false, stale: true },
    { name: "security-refresh-dark-horizontal", state: "security", dark: true, vertical: false, refreshing: true },
    { name: "security-stale-refresh-dark-horizontal", state: "security", dark: true, vertical: false, stale: true, refreshing: true },
    { name: "security-stale-refresh-transparent-horizontal", state: "security", transparent: true, vertical: false, stale: true, refreshing: true },
    { name: "watched-light-horizontal", state: "watched", dark: false, vertical: false },
    { name: "updates-contrast-horizontal", state: "updates", contrast: true, vertical: false },
    { name: "degraded-transparent-vertical", state: "degraded", transparent: true, vertical: true },
    { name: "clear-dark-vertical", state: "clear", dark: true, vertical: true }
  ]
  property var currentFixture: fixtures[captureIndex]
  BarStatusPresentation { id: presentation; serviceAvailable: true }
  Rectangle {
    id: stage; anchors.fill: root
    color: root.currentFixture.transparent ? "transparent" : (root.currentFixture.dark ? "#1a1d23" : (root.currentFixture.contrast ? "#050505" : "#f3f5f7"))
    Rectangle {
      id: bar
      property bool vertical: root.currentFixture.vertical
      x: 28; y: 18
      width: vertical ? 27 : stage.width - 56; height: vertical ? stage.height - 36 : 27
      radius: 6; color: root.currentFixture.transparent ? "#cc343a46" : (root.currentFixture.dark || root.currentFixture.contrast ? "#343a46" : "#d9dee7")
      Repeater { model: 4; Rectangle { width: 16; height: 16; radius: 4; color: root.currentFixture.dark || root.currentFixture.contrast ? "#b7c0cd" : "#4d5969"; x: bar.vertical ? 6 : 16 + index * 32; y: bar.vertical ? 12 + index * 28 : 6 } }
      Rectangle { width: 1; height: bar.vertical ? 1 : 16; color: root.currentFixture.dark || root.currentFixture.contrast ? "#687386" : "#8c98a8"; x: bar.vertical ? 0 : bar.width - 59; y: bar.vertical ? bar.height - 27 : 5 }
      Item {
        id: statusSlot; width: 27; height: 27
        x: bar.vertical ? 0 : bar.width - 43; y: bar.vertical ? bar.height - 27 : 0
        BarStatusIcon {
        id: statusIcon; anchors.centerIn: parent; width: 16; height: 16
        icon: presentation.status.icon; badge: presentation.status.badge; stale: presentation.status.stale; refreshing: presentation.status.spinner; reducedMotion: true
        foreground: root.currentFixture.dark || root.currentFixture.contrast || root.currentFixture.transparent ? "#f7f9fc" : "#172033"
        urgent: root.currentFixture.dark ? "#ff9990" : "#bd1830"
        fontFamily: root.productionIconFont; fontSize: 13
        }
      }
    }
    Rectangle {
      id: tooltip; x: bar.vertical ? 80 : 28; y: bar.vertical ? 18 : 64
      width: bar.vertical ? stage.width - 108 : stage.width - 56; height: bar.vertical ? stage.height - 36 : 128
      radius: 10; border.width: 1; border.color: root.currentFixture.dark || root.currentFixture.contrast ? "#59657a" : "#b9c2cf"
      color: root.currentFixture.dark || root.currentFixture.contrast ? "#2b313c" : "#ffffff"
      Text { id: tooltipText; anchors.fill: tooltip; anchors.margins: 18; text: presentation.status.tooltip; wrapMode: Text.WordWrap; maximumLineCount: 5; elide: Text.ElideRight; color: root.currentFixture.dark || root.currentFixture.contrast ? "#f7f9fc" : "#172033"; font.pixelSize: 15; verticalAlignment: Text.AlignVCenter; renderType: Text.QtRendering; visible: false }
    }
  }
  Component.onCompleted: captureNext()
  Timer { id: settle; interval: 120; repeat: false; onTriggered: stage.grabToImage(function(result) { result.saveToFile(root.outputDirectory + "/" + root.currentFixture.name + ".png"); root.captureIndex += 1; root.captureNext() }) }
  function captureNext() { if (captureIndex >= fixtures.length) { Qt.quit(); return }; presentation.refreshing = currentFixture.refreshing === true; presentation.snapshot = snapshot(currentFixture.state, currentFixture.stale === true); settle.start() }
  function snapshot(state, stale) {
    var summary = { securityFindings: 0, watchedUpdates: 0, totalUpdates: 0, degradedSources: 0 }
    if (state === "security") summary.securityFindings = 1
    if (state === "watched") { summary.watchedUpdates = 2; summary.totalUpdates = 2 }
    if (state === "updates") summary.totalUpdates = 4
    if (state === "degraded") summary.degradedSources = 1
    return { payload: { summary: summary, sources: [{ source: "security", status: "ok" }, { source: "omarchy", status: "ok" }, { source: "arch", status: state === "degraded" ? "offline" : (stale ? "stale" : "ok") }], findings: state === "security" ? [{ findings: [{ severity: "critical", fixedVersion: "1", status: "Fixed" }] }] : [] } }
  }
}
