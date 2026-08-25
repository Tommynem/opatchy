#!/usr/bin/env bash
set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly qml_test_root="${repository_root}/tests/qml"
readonly qt6_qmltestrunner="${OPATCHY_QMLTESTRUNNER:-/usr/lib/qt6/bin/qmltestrunner}"

if [[ ! -d "${qml_test_root}" ]] || ! find "${qml_test_root}" -type f -name '*.qml' -print -quit | grep -q .; then
    printf '%s\n' 'PENDING(integration): offscreen QML tests await Todo 5 lifecycle fixtures'
    exit 0
fi

if [[ ! -x "${qt6_qmltestrunner}" ]]; then
    printf 'ERROR(required capability): Qt 6 qmltestrunner is unavailable at %s\n' "${qt6_qmltestrunner}" >&2
    exit 127
fi

runner_help="$("${qt6_qmltestrunner}" -help 2>&1 || true)"
if [[ "${runner_help}" != *"-repeat n"* ]]; then
    printf 'ERROR(required capability): Qt 6 qmltestrunner is unavailable at %s\n' "${qt6_qmltestrunner}" >&2
    exit 127
fi

cd "${repository_root}"
QT_QPA_PLATFORM=offscreen "${qt6_qmltestrunner}" -input tests/qml
