#!/usr/bin/env bash
set -euo pipefail
readonly root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly output="${root}/.omo/evidence/task-24-opatchy/visual-qa/context"
readonly manifest="${output}/context.sha256"
mkdir -p "${output}"
rm -f "${output}"/*.png
cd "${root}"
QT_QPA_PLATFORM=offscreen qmlscene tests/qml/BarStatusContextCapture.qml
for capture in "${output}"/*transparent*.png; do
  alpha_range="$(identify -format '%[fx:minima.a] %[fx:maxima.a]' "${capture}")"
  [[ "${alpha_range}" == "0 1" ]] || { printf 'expected transparent pixels in %s, got alpha range %s\n' "${capture}" "${alpha_range}" >&2; exit 1; }
done
(
  cd "${root}"
  sha256sum qml/components/BarStatusIcon.qml qml/components/BarStatusPresentation.qml qml/models/BarStatusModel.js tests/qml/BarStatusContextCapture.qml
) >"${manifest}"
file "${output}"/*.png
identify -format '%f %wx%h\n' "${output}"/*.png
