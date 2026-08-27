#!/usr/bin/env bash
set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly virtual_environment="${repository_root}/.venv"
temporary_root=""
state_root=""
cache_root=""
hidden_virtual_environment=""
declare -a child_process_groups=()
readonly -a node_test_files=(
    tests/js/action-controller.test.mjs
    tests/js/harness.test.mjs
    tests/js/security-view-model.test.mjs
    tests/js/service-controller.test.mjs
    tests/js/star-view-model.test.mjs
    tests/js/tab-model.test.mjs
    tests/js/update-view-model.test.mjs
)
readonly -a qml_test_files=(
    tests/qml/tst_bar_status.qml
    tests/qml/tst_lifecycle.qml
    tests/qml/tst_panel_layout.qml
    tests/qml/tst_panel_shell.qml
    tests/qml/tst_security_view.qml
    tests/qml/tst_star_interaction.qml
    tests/qml/tst_tab_navigation.qml
)

restore_virtual_environment() {
    if [[ -n "${hidden_virtual_environment}" ]] && [[ -e "${hidden_virtual_environment}" ]]; then
        mv "${hidden_virtual_environment}" "${virtual_environment}"
        hidden_virtual_environment=""
    fi
}

cleanup() {
    local status="$?"

    trap - EXIT
    for process_group in "${child_process_groups[@]}"; do
        kill -TERM -- "-${process_group}" 2>/dev/null || true
    done
    restore_virtual_environment
    if [[ -n "${temporary_root}" ]]; then
        rm -rf "${temporary_root}"
    fi
    exit "${status}"
}

handle_signal() {
    exit 143
}

require_command() {
    local command_name="$1"

    if ! command -v "${command_name}" >/dev/null 2>&1; then
        printf 'ERROR(required capability): %s is unavailable\n' "${command_name}" >&2
        exit 127
    fi
}

run_gate() {
    local gate_name="$1"
    shift

    printf 'RUN(%s):' "${gate_name}"
    printf ' %q' "$@"
    printf '\n'
    setsid "$@" &
    local process_group="$!"
    local status
    child_process_groups+=("${process_group}")
    if wait "${process_group}"; then
        printf 'PASS(%s)\n' "${gate_name}"
        return 0
    else
        status="$?"
        printf 'FAIL(%s): command exited %s\n' "${gate_name}" "${status}" >&2
        exit "${status}"
    fi
}

run_qml_lint() {
    local -a qml_files=()
    mapfile -d '' qml_files < <(find . -type f -name '*.qml' -print0)
    if (( ${#qml_files[@]} == 0 )); then
        printf '%s\n' 'PENDING(integration): QML lint awaits Todo 5 lifecycle files'
        return 0
    fi

    require_command qmllint
    if [[ ! -d /usr/share/omarchy/shell ]]; then
        printf '%s\n' 'ERROR(required capability): /usr/share/omarchy/shell is unavailable' >&2
        exit 127
    fi
    run_gate qml qmllint -I /usr/share/omarchy/shell "${qml_files[@]}"
}

run_manifest_validation() {
    if [[ ! -f manifest.json ]]; then
        printf '%s\n' 'PENDING(integration): manifest validation awaits Todo 5 manifest.json'
        return 0
    fi

    require_command omarchy
    if [[ -e "${virtual_environment}" ]]; then
        hidden_virtual_environment="${temporary_root}/.venv"
        mv "${virtual_environment}" "${hidden_virtual_environment}"
    fi
    run_gate manifest omarchy plugin validate .
    restore_virtual_environment
}

trap cleanup EXIT
trap handle_signal HUP INT TERM

cd "${repository_root}"
temporary_root="$(mktemp -d "${TMPDIR:-/tmp}/opatchy-validate.XXXXXX")"
state_root="${temporary_root}/state"
cache_root="${temporary_root}/cache"
mkdir -p "${state_root}" "${cache_root}"
export XDG_STATE_HOME="${state_root}"
export XDG_CACHE_HOME="${cache_root}"

require_command uv
require_command node
if [[ ! -x /usr/bin/python3 ]]; then
    printf '%s\n' 'ERROR(required capability): /usr/bin/python3 is unavailable' >&2
    exit 127
fi

run_gate lock uv lock --check
run_gate environment uv sync --group dev --locked --check
run_gate format uv run --locked --no-sync ruff format --check .
run_gate lint uv run --locked --no-sync ruff check .
run_gate type uv run --locked --no-sync basedpyright
run_qml_lint
for qml_test_file in "${qml_test_files[@]}"; do
    if [[ ! -f "${qml_test_file}" ]]; then
        printf 'ERROR(required test): %s is unavailable\n' "${qml_test_file}" >&2
        exit 127
    fi
done
run_gate qml-offscreen "${repository_root}/scripts/qml_offscreen.sh"
run_manifest_validation
run_gate python-tests uv run --locked --no-sync pytest -q

if [[ -d helper/opatchy_helper ]]; then
    run_gate coverage uv run --locked --no-sync pytest -q --cov=helper/opatchy_helper --cov-report=term-missing
else
    printf '%s\n' 'PENDING(integration): 90% helper coverage awaits Todo 2 package'
fi

run_gate js node --test "${node_test_files[@]}" tests/js/*.test.mjs
run_gate repository-contract /usr/bin/python3 -m unittest discover -s tests/contract -p 'test_*.py'
run_gate runtime "${repository_root}/scripts/runtime_without_venv.sh"
run_gate static git diff --check
