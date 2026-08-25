#!/usr/bin/env bash
set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly qml_test_root="${repository_root}/tests/qml"

if [[ ! -d "${qml_test_root}" ]] || ! find "${qml_test_root}" -type f -name '*.qml' -print -quit | grep -q .; then
    printf '%s\n' 'PENDING(integration): offscreen QML tests await Todo 5 lifecycle fixtures'
    exit 0
fi

if ! command -v qmltestrunner >/dev/null 2>&1; then
    printf '%s\n' 'ERROR(required capability): qmltestrunner is unavailable' >&2
    exit 127
fi

cd "${repository_root}"
QT_QPA_PLATFORM=offscreen qmltestrunner -input tests/qml
