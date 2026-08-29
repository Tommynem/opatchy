#!/usr/bin/env bash
set -euo pipefail

readonly root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly screenshot_root="${root}/docs/screenshots"
readonly stage="$(mktemp -d)"
readonly fixture="${root}/tests/qml/Todo27PanelFixtureCapture.qml"
readonly qmlscene="/usr/lib/qt6/bin/qmlscene"
readonly source_manifest="${screenshot_root}/fixture-sources.sha256"
readonly -a captures=(clear dense-updates conditional-security stale-degraded)
readonly -a png_options=(-strip -define png:exclude-chunk=date,time -define png:compression-level=9)

cleanup() {
  rm -rf "${stage}"
}
trap cleanup EXIT

mkdir -p "${screenshot_root}"
[[ -x "${qmlscene}" ]] || { printf 'ERROR(required capability): %s is unavailable\n' "${qmlscene}" >&2; exit 127; }
mkdir -p "${stage}/raw"
cd "${root}"
QT_QPA_PLATFORM=offscreen "${qmlscene}" -I tests/qml/imports "${fixture}" "--output-directory=${stage}/raw"

for capture in "${captures[@]}"; do
  [[ -f "${stage}/raw/${capture}.png" ]] || { printf 'ERROR: fixture capture missing %s\n' "${capture}" >&2; exit 1; }
  magick "${stage}/raw/${capture}.png" "${png_options[@]}" "PNG32:${screenshot_root}/fixture-${capture}.png"
done

magick "${screenshot_root}/fixture-clear.png" "${screenshot_root}/fixture-dense-updates.png" +append "${png_options[@]}" "${stage}/top.png"
magick "${screenshot_root}/fixture-conditional-security.png" "${screenshot_root}/fixture-stale-degraded.png" +append "${png_options[@]}" "${stage}/bottom.png"
magick "${stage}/top.png" "${stage}/bottom.png" -append "${png_options[@]}" "PNG32:${root}/preview.png"
sha256sum Panel.qml qml/components/SourceContent.qml qml/components/UpdateListView.qml qml/components/SecurityView.qml qml/components/SecurityFindingRow.qml tests/qml/Todo27PanelFixtureCapture.qml >"${source_manifest}"
file "${root}/preview.png" "${screenshot_root}"/fixture-*.png
identify -format '%f %wx%h %[channels] %[opaque]\n' "${root}/preview.png" "${screenshot_root}"/fixture-*.png
