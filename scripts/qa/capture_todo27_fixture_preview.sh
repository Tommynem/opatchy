#!/usr/bin/env bash
set -euo pipefail

readonly root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly context_root="${root}/.omo/evidence/task-24-opatchy/visual-qa/context"
readonly screenshot_root="${root}/docs/screenshots"
readonly notice='ILLUSTRATIVE FIXTURE DATA - NOT A REAL HOST CAPTURE'
readonly stage="$(mktemp -d)"

cleanup() {
  rm -rf "${stage}"
}
trap cleanup EXIT

mkdir -p "${screenshot_root}"
bash "${root}/scripts/capture_bar_status_context.sh"

label_capture() {
  local source="$1" target="$2" title="$3"
  magick "${source}" -gravity north -background '#121820' -fill '#f5f7fb' -font DejaVu-Sans -pointsize 18 \
    label:"${notice}" -append -gravity north -background '#253348' -fill '#d7e4f7' -font DejaVu-Sans -pointsize 16 \
    label:"${title}" -append "PNG32:${target}"
}

label_capture "${context_root}/clear-dark-vertical.png" "${screenshot_root}/fixture-clear.png" "Clear state"
label_capture "${context_root}/updates-contrast-horizontal.png" "${screenshot_root}/fixture-updates.png" "Update state"
label_capture "${context_root}/security-stale-refresh-dark-horizontal.png" "${screenshot_root}/fixture-security-stale.png" "Security and stale state"
label_capture "${context_root}/security-stale-refresh-transparent-horizontal.png" "${screenshot_root}/fixture-transparent-stale.png" "Transparent stale state"
magick -size 1360x84 xc:'#0c1119' -gravity center -fill '#ffffff' -font DejaVu-Sans -pointsize 24 \
  -annotate 0 "OPATCHY PREVIEW - ${notice}" "${stage}/header.png"
magick "${screenshot_root}/fixture-clear.png" "${screenshot_root}/fixture-updates.png" +append "${stage}/top.png"
magick "${screenshot_root}/fixture-security-stale.png" "${screenshot_root}/fixture-transparent-stale.png" +append "${stage}/bottom.png"
magick "${stage}/header.png" "${stage}/top.png" "${stage}/bottom.png" -append "PNG32:${root}/preview.png"
file "${root}/preview.png" "${screenshot_root}"/*.png
identify -format '%f %wx%h %[channels]\n' "${root}/preview.png" "${screenshot_root}"/*.png
