#!/usr/bin/env bash
set -euo pipefail

readonly root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly stage="$(mktemp -d)"
readonly -a previews=(
  "${root}/preview.png"
  "${root}/docs/screenshots/fixture-clear.png"
  "${root}/docs/screenshots/fixture-dense-updates.png"
  "${root}/docs/screenshots/fixture-conditional-security.png"
  "${root}/docs/screenshots/fixture-stale-degraded.png"
)

cleanup() {
  rm -rf "${stage}"
}
trap cleanup EXIT

fixture_source="${root}/tests/qml/Todo27PanelFixtureCapture.qml"
capture_script="${root}/scripts/qa/capture_todo27_fixture_preview.sh"

[[ -f "${fixture_source}" ]]
! rg -Fq 'capture_bar_status_context.sh' "${capture_script}"
! rg -Fq '.omo/evidence/task-24-opatchy/visual-qa/context' "${capture_script}"
rg -Fq 'Todo27PanelFixtureCapture.qml' "${capture_script}"
rg -Fq 'sha256sum Panel.qml qml/components/SourceContent.qml qml/components/UpdateListView.qml qml/components/SecurityView.qml qml/components/SecurityFindingRow.qml' "${capture_script}"
rg -Fq 'panelLoader.setSource("../../Panel.qml"' "${fixture_source}"

bash "${capture_script}" >/dev/null
sha256sum "${previews[@]}" >"${stage}/first.sha256"
bash "${capture_script}" >/dev/null
sha256sum "${previews[@]}" >"${stage}/second.sha256"
cmp "${stage}/first.sha256" "${stage}/second.sha256"
sha256sum -c "${root}/docs/screenshots/fixture-sources.sha256" >/dev/null
! rg -n '/home/|/Users/|/private/|hostname|package inventory|task-24-opatchy' "${root}/docs/screenshots/fixture-sources.sha256"
! rg -n '/home/|/Users/|/private/|hostname|package inventory|real host capture' \
  "${fixture_source}" "${capture_script}" "${root}/docs/screenshots/fixture-provenance.md"
for preview in "${previews[@]}"; do
  file "${preview}" | grep -Fq 'PNG image data'
  identify -format '%w %h %[channels] %[opaque]\n' "${preview}" | grep -Eiq '^[1-9][0-9]* [1-9][0-9]* (s?rgba|rgba)( [0-9.]+)? (true|false)$'
  ! identify -verbose "${preview}" | rg -i 'png:(tIME|tEXt|zTXt|iTXt)|profile-icc|exif:'
  ! strings "${preview}" | rg -i '/home/|/Users/|/private/|hostname|package inventory|real host capture'
done
[[ "$(identify -format '%wx%h' "${root}/preview.png")" == '1520x1120' ]]
for preview in "${previews[@]:1}"; do
  [[ "$(identify -format '%wx%h' "${preview}")" == '760x560' ]]
done
rg -Fq 'ILLUSTRATIVE FIXTURE DATA - NOT A REAL HOST CAPTURE' "${root}/docs/screenshots/fixture-provenance.md"
printf '%s\n' 'PASS: Todo 27 production-panel fixture previews regenerate deterministically without private evidence'
