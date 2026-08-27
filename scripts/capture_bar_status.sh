#!/usr/bin/env bash
set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly relative_evidence='.omo/evidence/task-24-opatchy/visual-qa'
readonly generation_root="$(mktemp -d "${TMPDIR:-/tmp}/opatchy-bar-status.XXXXXXXX")"
readonly generation_id="$(date +%s%N)-$$"

cleanup() {
    rm -rf "${generation_root}"
}
trap cleanup EXIT

mkdir -p "${generation_root}/${relative_evidence}/png"
cd "${generation_root}"
QT_QPA_PLATFORM=offscreen qmlscene "${repository_root}/tests/qml/BarStatusCapture.qml"

{
    printf 'generation_id=%s\n' "${generation_id}"
    for source in qml/components/BarStatusPresentation.qml qml/components/BarStatusIcon.qml qml/models/BarStatusModel.js tests/qml/BarStatusCapture.qml; do
        sha256sum "${repository_root}/${source}"
    done
} >"${generation_root}/${relative_evidence}/generation.sha256"

OPATCHY_CAPTURE_ROOT="${generation_root}" OPATCHY_CAPTURE_GENERATION="${generation_id}" \
    bash "${repository_root}/scripts/verify_bar_status_captures.sh"

target_root="${repository_root}/${relative_evidence}"
rm -rf "${target_root}/png"
mv "${generation_root}/${relative_evidence}/png" "${target_root}/"
mv "${generation_root}/${relative_evidence}/matrix.tsv" "${target_root}/"
mv "${generation_root}/${relative_evidence}/generation.sha256" "${target_root}/"
