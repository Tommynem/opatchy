#!/usr/bin/env bash
set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly output_directory="${repository_root}/.omo/evidence/task-24-opatchy/visual-qa/png"

mkdir -p "${output_directory}"
rm -f "${output_directory}"/*.png
cd "${repository_root}"
QT_QPA_PLATFORM=offscreen qmlscene tests/qml/BarStatusCapture.qml
bash scripts/verify_bar_status_captures.sh
