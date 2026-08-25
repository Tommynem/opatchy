#!/usr/bin/env bash
set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly helper_entrypoint="${repository_root}/helper/opatchy.py"
readonly virtual_environment="${repository_root}/.venv"
hidden_virtual_environment=""
runtime_process_group=""
runtime_stdout=""
runtime_stderr=""

cleanup() {
    local status="$?"

    trap - EXIT
    if [[ -n "${runtime_process_group}" ]]; then
        kill -TERM -- "-${runtime_process_group}" 2>/dev/null || true
    fi
    if [[ -n "${hidden_virtual_environment}" ]] && [[ -e "${hidden_virtual_environment}" ]]; then
        mv "${hidden_virtual_environment}" "${virtual_environment}"
    fi
    if [[ -n "${runtime_stdout}" ]]; then
        rm -f "${runtime_stdout}"
    fi
    if [[ -n "${runtime_stderr}" ]]; then
        rm -f "${runtime_stderr}"
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

runtime_stdout="$(mktemp)"
runtime_stderr="$(mktemp)"

setsid /usr/bin/python3 "${helper_entrypoint}" snapshot >"${runtime_stdout}" 2>"${runtime_stderr}" &
runtime_process_group="$!"
if wait "${runtime_process_group}"; then
    status=0
else
    status="$?"
fi
runtime_process_group=""

if [[ "${status}" -eq 0 ]] && [[ ! -s "${runtime_stderr}" ]]; then
    printf '%s\n' 'PASS(runtime): plain /usr/bin/python3 completed with .venv hidden'
    exit 0
fi

if [[ "${status}" -eq 2 ]] && [[ ! -s "${runtime_stderr}" ]] && /usr/bin/python3 - "${runtime_stdout}" <<'PY'
import json
from pathlib import Path
import sys

payload = Path(sys.argv[1]).read_bytes()
try:
    text = payload.decode("utf-8")
    parsed = json.loads(text)
except (UnicodeDecodeError, json.JSONDecodeError):
    raise SystemExit(1)

if (
    payload.count(b"\n") != 1
    or not payload.endswith(b"\n")
    or type(parsed) is not dict
    or type(parsed.get("protocolVersion")) is not int
    or parsed.get("protocolVersion") != 1
    or parsed.get("kind") != "error"
    or type(parsed.get("error")) is not dict
    or parsed["error"].get("code") != "STATE_UNAVAILABLE"
):
    raise SystemExit(1)
PY
then
    printf '%s\n' 'PASS(runtime): plain /usr/bin/python3 returned STATE_UNAVAILABLE with .venv hidden'
    exit 0
fi

printf 'FAIL(runtime): plain /usr/bin/python3 smoke exited %s\n' "${status}" >&2
if [[ "${status}" -eq 0 ]]; then
    exit 1
fi
exit "${status}"
