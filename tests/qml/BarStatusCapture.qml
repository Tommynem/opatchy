import QtQuick 2.15
import QtQml 2.15
import "../../qml/components"

Item {
  id: root
  width: 192
  height: 56

  property int captureIndex: 0
  property string outputDirectory: ".omo/evidence/task-24-opatchy/visual-qa/png"
  property var fixtures: matrixFixtures()

  BarStatusPresentation {
    id: presentation
    serviceAvailable: true
  }

  Rectangle {
    id: surface
    anchors.fill: parent
    radius: fixture && fixture.layout === "narrow" ? 4 : 8
    color: fixture ? fixture.background : "transparent"
    property var fixture: root.fixtures[root.captureIndex]

    BarStatusIcon {
      anchors.centerIn: parent
      width: surface.fixture && surface.fixture.layout === "narrow" ? 28 : 34
      height: width
      icon: presentation.status.icon
      badge: presentation.status.badge
      stale: presentation.status.stale
      refreshing: presentation.status.spinner
      foreground: surface.fixture ? surface.fixture.foreground : "transparent"
      urgent: surface.fixture ? surface.fixture.urgent : "transparent"
    }

    Repeater {
      model: 6

      Rectangle {
        x: surface.width - 1 - index
        y: surface.height - 1
        width: 1
        height: 1
        color: Qt.rgba(signatureComponent(index, 0) / 255, signatureComponent(index, 1) / 255, signatureComponent(index, 2) / 255, 1)
      }
    }
  }

  Component.onCompleted: captureNext()

  function captureNext() {
    if (captureIndex >= fixtures.length) {
      Qt.quit()
      return
    }
    var fixture = fixtures[captureIndex]
    width = fixture.width
    height = fixture.height
    presentation.refreshing = fixture.refreshing
    presentation.snapshot = snapshotFor(fixture)
    Qt.callLater(function() {
      surface.grabToImage(function(result) {
        result.saveToFile(outputDirectory + "/" + fixture.name + ".png")
        captureIndex += 1
        captureNext()
      })
    })
  }

  function matrixFixtures() {
    var states = ["security", "watched", "updates", "degraded", "clear"]
    var themes = ["light", "dark", "contrast", "transparent"]
    var layouts = ["horizontal", "vertical", "narrow"]
    var fixtures = []
    for (var stateIndex = 0; stateIndex < states.length; stateIndex += 1)
      for (var themeIndex = 0; themeIndex < themes.length; themeIndex += 1)
        for (var layoutIndex = 0; layoutIndex < layouts.length; layoutIndex += 1)
          fixtures.push(fixtureFor(states[stateIndex], themes[themeIndex], layouts[layoutIndex]))
    return fixtures
  }

  function fixtureFor(state, theme, layout) {
    var tokens = themeTokens(theme)
    var geometry = layoutGeometry(layout)
    return {
      name: state + "-" + theme + "-" + layout,
      state: state,
      theme: theme,
      layout: layout,
      foreground: tokens.foreground,
      urgent: tokens.urgent,
      background: tokens.background,
      width: geometry.width,
      height: geometry.height,
      refreshing: state === "security" && theme === "dark" && layout === "horizontal",
      stale: state === "security" && theme === "dark" && layout === "horizontal"
    }
  }

  function themeTokens(theme) {
    if (theme === "light") return { foreground: "#1d1d1d", urgent: "#b00020", background: "#f7f7f7" }
    if (theme === "contrast") return { foreground: "#ffffff", urgent: "#ffff00", background: "#000000" }
    if (theme === "transparent") return { foreground: "#ffffff", urgent: "#ff6b6b", background: "transparent" }
    return { foreground: "#f5f5f5", urgent: "#ff6b6b", background: "#202124" }
  }

  function layoutGeometry(layout) {
    if (layout === "vertical") return { width: 56, height: 192 }
    if (layout === "narrow") return { width: 88, height: 56 }
    return { width: 192, height: 56 }
  }

  function snapshotFor(fixture) {
    var summary = { securityFindings: 0, watchedUpdates: 0, totalUpdates: 0, degradedSources: 0 }
    if (fixture.state === "security") summary.securityFindings = 1
    if (fixture.state === "watched") { summary.watchedUpdates = 2; summary.totalUpdates = 4 }
    if (fixture.state === "updates") summary.totalUpdates = 4
    if (fixture.state === "degraded") summary.degradedSources = 1
    var sources = [
      { source: "security", status: "ok" },
      { source: "omarchy", status: "ok" },
      { source: "arch", status: fixture.state === "degraded" ? "offline" : (fixture.stale ? "stale" : "ok") }
    ]
    var findings = fixture.state === "security" ? [{ findings: [{ severity: "critical", fixedVersion: "1.2.3", status: "Fixed" }] }] : []
    return { payload: { summary: summary, sources: sources, findings: findings } }
  }

  function signatureBit(bit) {
    var status = presentation.status
    if (bit >= 117) return badgeBit(status.badge, bit - 117)
    if (bit >= 114) return iconBit(status.icon, bit - 114)
    if (bit >= 10) return labelBit(status.label, bit - 10)
    var kinds = ["security", "watched", "updates", "degraded", "clear"]
    var themes = ["light", "dark", "contrast", "transparent"]
    var layouts = ["horizontal", "vertical", "narrow"]
    var code = kinds.indexOf(status.kind) + 1
    code += themes.indexOf(surface.fixture.theme) * 8
    code += layouts.indexOf(surface.fixture.layout) * 32
    if (status.stale) code += 128
    if (status.spinner) code += 256
    return (code & (1 << bit)) !== 0
  }

  function iconBit(icon, bit) {
    var icons = ["shield", "bookmark", "update", "warning", "check"]
    var code = icons.indexOf(icon) + 1
    return (code & (1 << bit)) !== 0
  }

  function badgeBit(badge, bit) {
    if (bit === 0) return badge !== ""
    var code = badge === "" ? 0 : Number(badge)
    return (code & (1 << (bit - 1))) !== 0
  }

  function labelBit(label, bit) {
    if (bit < 8) return (label.length & (1 << bit)) !== 0
    var character = Math.floor((bit - 8) / 16)
    var characterBit = (bit - 8) % 16
    var code = character < label.length ? label.charCodeAt(character) : 0
    return (code & (1 << characterBit)) !== 0
  }

  function signatureComponent(pixel, channel) {
    var value = 0
    var offset = (pixel * 3 + channel) * 8
    for (var bit = 0; bit < 8; bit += 1)
      if (offset + bit < 128 && signatureBit(offset + bit)) value += 1 << bit
    return value
  }
}
