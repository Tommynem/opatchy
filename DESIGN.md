# Opatchy Design System

## 1. Atmosphere & Identity

Opatchy is a quiet, host-native operations panel: compact evidence first, with
meaning carried by explicit text rather than color or decoration. Its signature
is a readable evidence trail that remains clear when data is current, retained,
or unavailable.

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

Use `Style.spacing.xs` for evidence within a finding and `Style.spacing.sm` for
groups and controls. The panel is one responsive column; all children bind to
their parent width and long external text wraps, elides, and has a bounded line
count.

## 5. Components

### Source Tab Strip
- **Structure**: horizontal native `Button` list.
- **States**: selected, focus, disabled.
- **Accessibility**: keyboard focus and textual health.

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
feedback; no layout property is animated.

## 7. Depth & Surface

Use the host's tonal panel and native control surfaces. Opatchy adds no custom
shadows, borders, or color literals.

## 8. Accessibility Constraints & Accepted Debt

The UI targets keyboard-complete navigation, visible host-native focus, plain
external text, bounded hostile strings, and non-color status copy. Standalone
Qt tests verify presentation seams; compositor and screen-reader signoff remain
host-level validation outside this repository's offscreen capability.
