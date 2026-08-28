# Opatchy Design System

## 1. Atmosphere & Identity

Opatchy is a quiet, host-native operations panel. Its focal hierarchy starts
with one evidence summary, then a plainly labelled problem or current-state
message, then the selected source. Meaning is carried by explicit text and
Nerd Font glyphs rather than color or decoration, so current, retained,
unavailable, and incompatible evidence cannot be mistaken for one another.

## 2. Color

| Role | Token | Usage |
| --- | --- | --- |
| Primary text | `Color.foreground` | Titles, labels, controls |
| Secondary text | `Qt.darker(Color.foreground, 1.4)` | Metadata and source coverage |
| Interactive foreground | `Button.foreground` | Native controls and links |

Use only Omarchy `Color` and native `Button` theme behavior. Status is always
expressed in copy and glyphs, never color alone.

## 3. Typography

| Level | Token | Usage |
| --- | --- | --- |
| Body | `Style.font.body` | Package and advisory labels |
| Body small | `Style.font.bodySmall` | Evidence, source coverage, buttons |
| Caption | `Style.font.caption` | Provenance and identity metadata |

The inherited panel font is `bar.fontFamily`, falling back to
`Style.font.family`. External text uses `Text.PlainText` and is bounded before
rendering.

## 4. Spacing & Layout

Use `Style.spacing.xs` within an evidence row and `Style.spacing.sm` between
the hero, problem summary, tab grid, and selected source. The panel is one
responsive column; all children bind to their parent width and long external
text wraps, elides, and has a bounded line count. Tab navigation uses three,
two, or one columns according to the token-derived minimum readable tab width;
narrow panels use one column so health text wraps visibly instead of being
clipped or hidden behind a tooltip. It never horizontally clips a tab strip.

## 5. Components

### Source Tab Strip
- **Structure**: responsive native `Button` grid in the mandatory Security,
  Omarchy, System, AUR, Flatpak, mise order. It uses three columns only when
  the token-derived cell width remains readable, then two or one columns.
- **States**: selected, focus, current, last-known, unavailable, incompatible,
  and not-applicable health.
- **Accessibility**: every tab remains discoverable without horizontal
  scrolling; its bounded visible glyph, name/count, and health text identify
  state for keyboard users, while the tooltip supplements rather than replaces
  that text. Native Enter and Space activation remain on the host button.

### Panel Problem Summary
- **Structure**: one leading Nerd Font warning glyph followed by a short,
  problem-first title, an actionable explanation, and one scan-evidence line.
- **States**: all current, source attention required, update required, and
  service unavailable.
- **Accessibility**: problem state is named in text and glyph shape, never
  color alone. It is the only panel-global failure message, preventing repeated
  incompatible/unavailable prose.

### Empty Evidence State
- **Structure**: a short outcome title followed by one source-specific next
  step, rather than blank space or repeated source-health metadata.
- **States**: no actionable updates, no watched items, no cached matches.
- **Accessibility**: the title and detail remain plain text and fit the same
  bounded responsive column as populated rows.

### Bar Status Indicator
- **Structure**: `BarStatusPresentation` provides one Nerd Fonts MDI glyph,
  badge, tooltip, stale marker, and spinner projection for the host
  `WidgetButton`. Use the host `monospace` fontconfig alias at 13px in a
  centered 16px glyph slot within the host's 27px bar button: shield-alert
  `󰻌` (`f0ecc`), bookmark `󰃀` (`f00c0`), package `󰏖` (`f03d6`), alert `󰀦`
  (`f0026`), and check-circle `󰗠` (`f05e0`). The 8px upper-left Clock Outline
  `󰅐` (`f0150`) indicates last-known data; the 8px upper-right Refresh `󰑐`
  (`f0450`) indicates scanning and rotates only when reduced motion is off.
  Do not use custom-drawn status geometry.
- **States**: high/critical security, watched update, ordinary update,
  mandatory-source degradation, clear, and unavailable in that precedence.
- **Accessibility**: every state names its counts and retained-data condition in
  the tooltip; urgent uses `bar.urgent`, all other states use `bar.foreground`.

### Evidence Row
- **Structure**: title followed by plain-text metadata.
- **States**: current, last-known, unknown, empty.
- **Accessibility**: status and provenance use text, never color alone.

### Native Action Button
- **Structure**: themed `qs.Ui.Button` within `BoundedControlStack`.
- **States**: default, focus, disabled.
- **Accessibility**: native Enter/Space behavior and tooltips.

### Identifier Link
- **Structure**: native button using a canonical identifier.
- **States**: enabled only for a link constructed by policy.
- **Accessibility**: the visible identifier and tooltip name the destination.

## 6. Motion & Interaction

No decorative motion is used. Native controls retain host focus and press
feedback; no layout property is animated. The host `md-refresh` glyph
(`\uf0450`) remains visible for refresh whether or not reduced motion disables
the separate bar refresh rotation.

## 7. Depth & Surface

Use the host's tonal panel and native control surfaces. Opatchy adds no custom
shadows, borders, or color literals.

## 8. Accessibility Constraints & Accepted Debt

The UI targets keyboard-complete navigation, visible host-native focus, plain
external text, bounded hostile strings, and non-color status copy. It must
remain usable at narrow widths, with CJK/RTL/long labels, and when reduced
motion is enabled. Standalone Qt tests verify presentation seams; compositor
and screen-reader signoff remain host-level validation outside this repository's
offscreen capability. Human visual approval and real-host compatibility remain
explicitly unproven by this contract.
