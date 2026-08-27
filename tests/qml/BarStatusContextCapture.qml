import QtQuick 2.15
import QtQml 2.15
import "../../qml/components"

Item {
  id: root
  width: 680; height: 280
  property int captureIndex: 0
  property string outputDirectory: ".omo/evidence/task-24-opatchy/visual-qa/context"
  property var fixtures: [
    { name: "security-dark-horizontal", state: "security", dark: true, vertical: false, refreshing: true },
    { name: "watched-light-horizontal", state: "watched", dark: false, vertical: false },
    { name: "updates-contrast-horizontal", state: "updates", contrast: true, vertical: false },
    { name: "degraded-transparent-vertical", state: "degraded", transparent: true, vertical: true },
    { name: "clear-dark-vertical", state: "clear", dark: true, vertical: true }
  ]
  property var currentFixture: fixtures[captureIndex]
  BarStatusPresentation { id: presentation; serviceAvailable: true }
  Rectangle {
    id: stage; anchors.fill: root
    color: root.currentFixture.transparent ? "#aeb9c8" : (root.currentFixture.dark ? "#1a1d23" : (root.currentFixture.contrast ? "#050505" : "#f3f5f7"))
    Rectangle {
      id: bar
      property bool vertical: root.currentFixture.vertical
      x: vertical ? 28 : 28; y: vertical ? 18 : 24
      width: vertical ? 68 : stage.width - 56; height: vertical ? stage.height - 36 : 58
      radius: 10; color: root.currentFixture.dark || root.currentFixture.transparent ? "#343a46" : "#d9dee7"
      Repeater { model: 4; Rectangle { width: 26; height: 26; radius: 7; color: root.currentFixture.dark ? "#b7c0cd" : "#4d5969"; x: bar.vertical ? 21 : 22 + index * 52; y: bar.vertical ? 18 + index * 48 : 16 } }
      Rectangle { width: 1; height: bar.vertical ? 1 : 30; color: root.currentFixture.dark ? "#687386" : "#8c98a8"; x: bar.vertical ? 0 : bar.width - 106; y: bar.vertical ? bar.height - 78 : 14 }
      BarStatusIcon {
        id: statusIcon; width: 28; height: 28
        x: bar.vertical ? 20 : bar.width - 82; y: bar.vertical ? bar.height - 58 : 15
        icon: presentation.status.icon; badge: presentation.status.badge; stale: presentation.status.stale; refreshing: presentation.status.spinner
        foreground: root.currentFixture.dark || root.currentFixture.contrast || root.currentFixture.transparent ? "#f7f9fc" : "#172033"
        urgent: root.currentFixture.dark ? "#ff9990" : "#bd1830"
      }
      Text { visible: !bar.vertical; x: bar.width - 48; y: 23; text: "Opatchy"; color: statusIcon.foreground; font.pixelSize: 10 }
    }
    Rectangle {
      id: tooltip; x: bar.vertical ? 126 : 28; y: bar.vertical ? 18 : 108
      width: bar.vertical ? stage.width - 154 : stage.width - 56; height: bar.vertical ? stage.height - 36 : 142
      radius: 10; border.width: 1; border.color: root.currentFixture.dark || root.currentFixture.contrast ? "#59657a" : "#b9c2cf"
      color: root.currentFixture.dark || root.currentFixture.contrast ? "#2b313c" : "#ffffff"
      Text { id: tooltipText; anchors.fill: tooltip; anchors.margins: 18; text: presentation.status.tooltip; wrapMode: Text.WordWrap; maximumLineCount: 5; elide: Text.ElideRight; color: root.currentFixture.dark || root.currentFixture.contrast ? "#f7f9fc" : "#172033"; font.pixelSize: 15; verticalAlignment: Text.AlignVCenter }
    }
  }
  Component.onCompleted: captureNext()
  Timer { id: settle; interval: 120; repeat: false; onTriggered: stage.grabToImage(function(result) { result.saveToFile(root.outputDirectory + "/" + root.currentFixture.name + ".png"); root.captureIndex += 1; root.captureNext() }) }
  function captureNext() { if (captureIndex >= fixtures.length) { Qt.quit(); return }; presentation.refreshing = currentFixture.refreshing === true; presentation.snapshot = snapshot(currentFixture.state, currentFixture.refreshing === true); settle.start() }
  function snapshot(state, stale) {
    var summary = { securityFindings: 0, watchedUpdates: 0, totalUpdates: 0, degradedSources: 0 }
    if (state === "security") summary.securityFindings = 1
    if (state === "watched") { summary.watchedUpdates = 2; summary.totalUpdates = 2 }
    if (state === "updates") summary.totalUpdates = 4
    if (state === "degraded") summary.degradedSources = 1
    return { payload: { summary: summary, sources: [{ source: "security", status: "ok" }, { source: "omarchy", status: "ok" }, { source: "arch", status: state === "degraded" ? "offline" : (stale ? "stale" : "ok") }], findings: state === "security" ? [{ findings: [{ severity: "critical", fixedVersion: "1", status: "Fixed" }] }] : [] } }
  }
}
