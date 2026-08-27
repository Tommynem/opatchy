import QtQuick 2.15
import QtTest 1.3
import "../../qml/components"
import "../../qml/models/BarStatusModel.js" as BarStatusModel

TestCase {
  id: root
  name: "OpatchyBarStatus"
  when: true

  Component {
    id: presentationComponent
    BarStatusPresentation { }
  }

  Component {
    id: iconComponent
    BarStatusIcon {
      width: 16
      height: 16
      icon: "shield"
      foreground: "white"
      urgent: "red"
      fontFamily: "monospace"
      fontSize: 13
    }
  }

  function snapshot(summary, archStatus, findings) {
    return {
      payload: {
        summary: summary,
        findings: findings || [],
        sources: [
          { source: "security", status: "ok" },
          { source: "omarchy", status: "ok" },
          { source: "arch", status: archStatus || "ok" }
        ]
      }
    }
  }

  function test_presentation_keeps_glyph_badge_tooltip_and_spinner_in_one_view() {
    const presentation = presentationComponent.createObject(root, {
      snapshot: snapshot({ securityFindings: 0, watchedUpdates: 0, totalUpdates: 2, degradedSources: 0 }),
      refreshing: true,
      serviceAvailable: true
    })

    compare(presentation.status.kind, "updates")
    compare(presentation.status.glyph, "^")
    compare(presentation.status.badge, "2")
    compare(presentation.status.spinner, true)
    compare(presentation.status.label, "^2 …")
    verify(presentation.status.tooltip.indexOf("2 other updates") !== -1)
    presentation.destroy()
  }

  function test_presentation_uses_source_evidence_for_a_stale_marker() {
    const fixture = snapshot({ securityFindings: 0, watchedUpdates: 0, totalUpdates: 5, degradedSources: 1 }, "stale")
    verify(Array.isArray(fixture.payload.sources))
    compare(fixture.payload.sources[2].status, "stale")
    compare(BarStatusModel.status(fixture, false, true).stale, true)
    const presentation = presentationComponent.createObject(root, { snapshot: fixture, serviceAvailable: true })
    compare(presentation.status.stale, true)
    verify(presentation.status.label.indexOf("~") !== -1)
    presentation.destroy()
  }

  function test_icon_exposes_stale_and_refresh_marks_independently() {
    const icon = iconComponent.createObject(null)
    const staleMarker = findChild(icon, "staleMarker")
    const refreshIndicator = findChild(icon, "refreshIndicator")

    verify(staleMarker !== null)
    verify(refreshIndicator !== null)

    icon.stale = true
    icon.refreshing = false
    wait(0)
    compare(icon.stale, true)
    compare(staleMarker.visible, true)
    compare(refreshIndicator.visible, false)

    icon.stale = false
    icon.refreshing = true
    wait(0)
    compare(staleMarker.visible, false)
    compare(refreshIndicator.visible, true)

    icon.stale = true
    icon.refreshing = true
    wait(0)
    compare(staleMarker.visible, true)
    compare(refreshIndicator.visible, true)
    compare(staleMarker.text, "↶")
    compare(refreshIndicator.text, "…")
    icon.destroy()
  }

}
