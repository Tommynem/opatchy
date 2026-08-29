# Fixture Screenshot Provenance

`scripts/qa/capture_todo27_fixture_preview.sh` renders
`tests/qml/Todo27PanelFixtureCapture.qml` with Qt 6's offscreen renderer and
the repository's test-only Omarchy module facades. The fixture instantiates the
current production `Panel.qml`, which composes `SourceContent`, `UpdateListView`,
`SecurityView`, and `SecurityFindingRow`. `fixture-sources.sha256` records the
listed key production and fixture source inputs used when the public artifacts
were generated.

Every image says `ILLUSTRATIVE FIXTURE DATA - NOT A REAL HOST CAPTURE`. The data
is invented and bounded: clear, 150-row dense update, conditional fixed-version
watch, and stale/degraded evidence states. The conditional-security state only
shows the existing UI action; it makes no installation, remediation, or safety
claim.

The capture freezes fixture service state, selection, and reduced motion. Its
dates are deliberately unrecorded so age copy is stable. Each publish pass strips
variable PNG chunks and emits RGBA PNGs with these stable dimensions:

| Artifact | Dimensions | Channel type |
| --- | --- | --- |
| `fixture-clear.png` | 760 x 560 | RGBA |
| `fixture-dense-updates.png` | 760 x 560 | RGBA |
| `fixture-conditional-security.png` | 760 x 560 | RGBA |
| `fixture-stale-degraded.png` | 760 x 560 | RGBA |
| `../../preview.png` | 1520 x 1120 | RGBA |

Raw renderer output stays in a temporary directory and is never published. The
regression script regenerates the set twice, compares SHA-256 hashes, verifies
these file properties, rejects metadata/private-path markers, and rejects the
obsolete Task 24 bar-context dependency. This is deterministic fixture evidence,
not a live-host or subjective visual-QA result.
