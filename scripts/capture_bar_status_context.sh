#!/usr/bin/env bash
set -euo pipefail
readonly root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly output="${root}/.omo/evidence/task-24-opatchy/visual-qa/context"
readonly manifest="${output}/context.sha256"
mkdir -p "${output}"
rm -f "${output}"/*.png
cd "${root}"
QT_QPA_PLATFORM=offscreen qmlscene tests/qml/BarStatusContextCapture.qml
sha256sum "${root}/qml/components/BarStatusIcon.qml" "${root}/qml/components/BarStatusPresentation.qml" "${root}/qml/models/BarStatusModel.js" "${root}/tests/qml/BarStatusContextCapture.qml" >"${manifest}"
file "${output}"/*.png
identify -format '%f %wx%h\n' "${output}"/*.png
