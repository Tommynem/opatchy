#!/usr/bin/env bash
set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly helper_entrypoint="${repository_root}/helper/opatchy.py"
readonly virtual_environment="${repository_root}/.venv"
hidden_virtual_environment=""
runtime_process_group=""

cleanup() {
    local status="$?"

    trap - EXIT
    if [[ -n "${runtime_process_group}" ]]; then
        kill -TERM -- "-${runtime_process_group}" 2>/dev/null || true
    fi
    if [[ -n "${hidden_virtual_environment}" ]] && [[ -e "${hidden_virtual_environment}" ]]; then
        mv "${hidden_virtual_environment}" "${virtual_environment}"
    fi
    exit "${status}"
}

trap cleanup EXIT

if [[ ! -f "${helper_entrypoint}" ]]; then
    printf '%s\n' 'PENDING(integration): runtime smoke awaits Todo 2 helper/opatchy.py'
    exit 0
fi

if [[ ! -x /usr/bin/python3 ]]; then
    printf '%s\n' 'ERROR(required capability): /usr/bin/python3 is unavailable' >&2
    exit 127
fi

if [[ -e "${virtual_environment}" ]]; then
    hidden_virtual_environment="${repository_root}/.venv.runtime-smoke.$$"
    mv "${virtual_environment}" "${hidden_virtual_environment}"
fi

unset PYTHONPATH VIRTUAL_ENV
export PYTHONNOUSERSITE=1

setsid /usr/bin/python3 "${helper_entrypoint}" snapshot &
runtime_process_group="$!"
if wait "${runtime_process_group}"; then
    runtime_process_group=""
else
    status="$?"
    printf 'FAIL(runtime): plain /usr/bin/python3 smoke exited %s\n' "${status}" >&2
    exit "${status}"
fi

printf '%s\n' 'PASS(runtime): plain /usr/bin/python3 completed with .venv hidden'
