#!/usr/bin/env bash
set -euo pipefail
readonly root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly output="${root}/.omo/evidence/task-24-opatchy/visual-qa/context"
mkdir -p "${output}"
rm -f "${output}"/*.png
cd "${root}"
QT_QPA_PLATFORM=offscreen qmlscene tests/qml/BarStatusContextCapture.qml
file "${output}"/*.png
identify -format '%f %wx%h\n' "${output}"/*.png
