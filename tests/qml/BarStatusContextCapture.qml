import QtQuick 2.15
import QtQml 2.15
import "../../qml/components"

Item {
  id: root
  width: 520
  height: 150
  property int index: 0
  property string outputDirectory: ".omo/evidence/task-24-opatchy/visual-qa/context"
  property var fixtures: [
    { name: "security-dark-horizontal", state: "security", dark: true, vertical: false, refreshing: true },
    { name: "watched-light-horizontal", state: "watched", dark: false, vertical: false },
    { name: "updates-contrast-horizontal", state: "updates", contrast: true, vertical: false },
    { name: "degraded-transparent-vertical", state: "degraded", transparent: true, vertical: true },
    { name: "clear-dark-vertical", state: "clear", dark: true, vertical: true }
  ]
  BarStatusPresentation { id: presentation; serviceAvailable: true }
  Rectangle {
    id: stage
    anchors.fill: parent
    color: fixture && fixture.transparent ? "transparent" : (fixture && fixture.dark ? "#202124" : (fixture && fixture.contrast ? "#000000" : "#f7f7f7"))
    property var fixture: root.fixtures[root.index]
    Rectangle {
      id: bar
      x: fixture && fixture.vertical ? 16 : 16
      y: fixture && fixture.vertical ? 12 : 14
      width: fixture && fixture.vertical ? 56 : parent.width - 32
      height: fixture && fixture.vertical ? parent.height - 24 : 48
      radius: 8
      color: fixture && fixture.transparent ? "#30343b" : (fixture && fixture.dark ? "#30343b" : "#e5e7eb")
      Repeater {
        model: 3
        Rectangle {
          width: 20; height: 20; radius: 10
          color: fixture && fixture.dark ? "#aeb4bd" : "#555b66"
          x: fixture && fixture.vertical ? 18 : 24 + index * 52
          y: fixture && fixture.vertical ? 22 + index * 52 : 14
        }
      }
      BarStatusIcon {
        width: 28; height: 28
        x: fixture && fixture.vertical ? 14 : bar.width - 70
        y: fixture && fixture.vertical ? bar.height - 42 : 10
        icon: presentation.status.icon; badge: presentation.status.badge
        stale: presentation.status.stale; refreshing: presentation.status.spinner
        foreground: fixture && fixture.dark ? "#f5f5f5" : "#1d1d1d"
        urgent: fixture && fixture.dark ? "#ff8a80" : "#b00020"
      }
      Text {
        visible: !(fixture && fixture.vertical)
        x: bar.width - 38; y: 17; text: "Opatchy"
        color: fixture && fixture.dark ? "#f5f5f5" : "#1d1d1d"; font.pixelSize: 10
      }
    }
    Rectangle {
      x: fixture && fixture.vertical ? 96 : 32; y: fixture && fixture.vertical ? 24 : 78
      width: fixture && fixture.vertical ? 390 : parent.width - 64; height: fixture && fixture.vertical ? 96 : 54
      radius: 6; color: fixture && fixture.dark ? "#353a43" : "#ffffff"
      Text { anchors.fill: parent; anchors.margins: 10; wrapMode: Text.WordWrap; text: presentation.status.tooltip; color: fixture && fixture.dark ? "#f5f5f5" : "#1d1d1d"; font.pixelSize: 11 }
    }
  }
  Component.onCompleted: captureNext()
  Timer { id: settle; interval: 80; repeat: false; onTriggered: stage.grabToImage(function(result) { result.saveToFile(outputDirectory + "/" + fixtures[index].name + ".png"); index += 1; captureNext() }) }
  function captureNext() {
    if (index >= fixtures.length) { Qt.quit(); return }
    var fixture = fixtures[index]
    presentation.refreshing = fixture.refreshing === true
    presentation.snapshot = snapshot(fixture.state, fixture.refreshing === true)
    settle.start()
  }
  function snapshot(state, stale) {
    var summary = { securityFindings: 0, watchedUpdates: 0, totalUpdates: 0, degradedSources: 0 }
    if (state === "security") summary.securityFindings = 1
    if (state === "watched") { summary.watchedUpdates = 2; summary.totalUpdates = 2 }
    if (state === "updates") summary.totalUpdates = 4
    if (state === "degraded") summary.degradedSources = 1
    return { payload: { summary: summary, sources: [{ source: "security", status: "ok" }, { source: "omarchy", status: "ok" }, { source: "arch", status: state === "degraded" ? "offline" : (stale ? "stale" : "ok") }], findings: state === "security" ? [{ findings: [{ severity: "critical", fixedVersion: "1", status: "Fixed" }] }] : [] } }
  }
}
