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

  TextMetrics { id: shieldMetrics; font.family: "monospace"; font.pixelSize: 13; text: "󰻌" }
  TextMetrics { id: staleMetrics; font.family: "monospace"; font.pixelSize: 8; text: "󰅐" }
  TextMetrics { id: refreshMetrics; font.family: "monospace"; font.pixelSize: 8; text: "󰑐" }
  TextMetrics { id: badgeMetrics; font.family: "monospace"; font.pixelSize: 9; font.bold: true; text: "1" }

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

  Component {
    id: statusSlotComponent
    Item {
      width: 27
      height: 27

      BarStatusIcon {
        objectName: "statusIcon"
        anchors.centerIn: parent
        width: 16
        height: 16
        icon: "shield"
        badge: "1"
        stale: true
        refreshing: true
        foreground: "white"
        urgent: "red"
        fontFamily: "monospace"
        fontSize: 13
      }
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

  function inkBounds(position, textItem, metrics) {
    return {
      x: position.x + metrics.tightBoundingRect.x,
      y: position.y + textItem.baselineOffset + metrics.tightBoundingRect.y,
      width: metrics.tightBoundingRect.width,
      height: metrics.tightBoundingRect.height
    }
  }

  function boundsOverlap(first, second) {
    return first.x < second.x + second.width
      && first.x + first.width > second.x
      && first.y < second.y + second.height
      && first.y + first.height > second.y
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
    compare(staleMarker.text, "󰅐")
    compare(refreshIndicator.text, "󰑐")
    compare(staleMarker.font.pixelSize, 8)
    compare(refreshIndicator.font.pixelSize, 8)
    icon.destroy()
  }

  function test_refresh_rotation_stops_for_reduced_motion_without_hiding_the_glyph() {
    const icon = iconComponent.createObject(null)
    const refreshIndicator = findChild(icon, "refreshIndicator")
    const refreshRotation = findChild(icon, "refreshRotation")

    verify(refreshIndicator !== null)
    verify(refreshRotation !== null)
    icon.refreshing = true
    wait(0)
    compare(refreshRotation.running, true)

    icon.reducedMotion = true
    wait(0)
    compare(refreshRotation.running, false)
    compare(refreshIndicator.visible, true)
    compare(refreshIndicator.rotation, 0)
    icon.destroy()
  }

  function test_icon_uses_distinct_host_slot_territories() {
    const slot = statusSlotComponent.createObject(root)
    const icon = findChild(slot, "statusIcon")
    const primaryGlyph = findChild(icon, "primaryGlyph")
    const staleMarker = findChild(icon, "staleMarker")
    const refreshIndicator = findChild(icon, "refreshIndicator")
    const statusBadge = findChild(icon, "statusBadge")

    verify(icon !== null)
    verify(primaryGlyph !== null)
    verify(staleMarker !== null)
    verify(refreshIndicator !== null)
    verify(statusBadge !== null)
    wait(0)

    const glyphPosition = primaryGlyph.mapToItem(slot, 0, 0)
    const stalePosition = staleMarker.mapToItem(slot, 0, 0)
    const refreshPosition = refreshIndicator.mapToItem(slot, 0, 0)
    const badgePosition = statusBadge.mapToItem(slot, 0, 0)
    const glyphCenterX = glyphPosition.x + primaryGlyph.width / 2
    const glyphCenterY = glyphPosition.y + primaryGlyph.height / 2

    verify(stalePosition.x > 0)
    verify(stalePosition.y > 0)
    verify(stalePosition.x + staleMarker.width < slot.width)
    verify(stalePosition.y + staleMarker.height < slot.height)
    verify(refreshPosition.x > 0)
    verify(refreshPosition.x + refreshIndicator.width < slot.width)
    verify(refreshPosition.y > 0)
    verify(refreshPosition.y + refreshIndicator.height < slot.height)
    verify(badgePosition.x > 0)
    verify(badgePosition.y > 0)
    verify(badgePosition.x + statusBadge.width < slot.width)
    verify(slot.height - (badgePosition.y + statusBadge.height) >= 4)
    verify(stalePosition.x + staleMarker.width < refreshPosition.x)
    verify(stalePosition.x + staleMarker.width / 2 < glyphCenterX)
    verify(stalePosition.y + staleMarker.height / 2 < glyphCenterY)
    verify(refreshPosition.x + refreshIndicator.width / 2 > glyphCenterX)
    verify(refreshPosition.y + refreshIndicator.height / 2 < glyphCenterY)
    verify(badgePosition.x + statusBadge.width / 2 > glyphCenterX)
    verify(badgePosition.y + statusBadge.height / 2 > glyphCenterY)
    const primaryBounds = inkBounds(glyphPosition, primaryGlyph, shieldMetrics)
    verify(!boundsOverlap(primaryBounds, inkBounds(badgePosition, statusBadge, badgeMetrics)))
    const staleBounds = inkBounds(stalePosition, staleMarker, staleMetrics)
    verify(!boundsOverlap(primaryBounds, staleBounds))
    const refreshBounds = inkBounds(refreshPosition, refreshIndicator, refreshMetrics)
    verify(!boundsOverlap(primaryBounds, refreshBounds))
    slot.destroy()
  }

}
