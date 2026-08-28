#!/usr/bin/env bash
set -euo pipefail

readonly plugin_id="io.github.tomge.opatchy"
readonly -a retained_ids=(
  "akitaonrails.ai-usagebar"
  "io.github.sirjul1337.lock-explorer"
  "mirador"
  "omaplug"
  "jkoestinger.vpn"
)

host=""
approval=""
plugin_source=""
record_dir=""
execute=false
backup_ready=false
mutated=false
restoring=false
monitor_pid=""

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage:
  todo27-real-shell-window.sh --host tomarchy|gomarchy --approval WINDOW-ID \
    --plugin-source /absolute/path/to/opatchy --record-dir /absolute/private/path --execute

This later-window runner changes only the local host selected by the user. It never
opens an update handoff. Do not run it until that host has an explicit, scheduled
approval window. The runner restores the prior shell config and target plugin state
on every exit after a mutation begins.
EOF
}

json_digest() {
  python3 -c 'import hashlib,json,sys; print(hashlib.sha256(json.dumps(json.load(sys.stdin), sort_keys=True, separators=(",", ":")).encode()).hexdigest())' <"$1"
}

plugin_digest() {
  local directory="$1"
  if [[ -L "${directory}" ]]; then
    printf 'symlink found in plugin directory: %s\n' "${directory}" >&2
    return 1
  fi
  if [[ ! -e "${directory}" ]]; then
    printf '%s\n' absent
    return
  fi
  if find "${directory}" -type l -print -quit | grep -q .; then
    printf 'symlink found in plugin directory: %s\n' "${directory}" >&2
    return 1
  fi
  (
    cd "${directory}"
    find . -type f -print0 | LC_ALL=C sort -z | xargs -r -0 sha256sum
  ) | sha256sum | cut -d' ' -f1
}

config_contains_ids() {
  python3 -c '
import json
import sys

document = json.load(open(sys.argv[1], encoding="utf-8"))
expected = set(sys.argv[2:])
found = set()

def visit(value):
    if isinstance(value, dict):
        identifier = value.get("id")
        if isinstance(identifier, str):
            found.add(identifier)
        for child in value.values():
            visit(child)
    elif isinstance(value, list):
        for child in value:
            visit(child)

visit(document)
missing = expected - found
if missing:
    raise SystemExit("missing retained plugin ids: " + ", ".join(sorted(missing)))
' "${shell_json}" "$@"
}

target_is_right_widget() {
  python3 -c '
import json
import sys

document = json.load(open(sys.argv[1], encoding="utf-8"))
layout = document.get("bar", {}).get("layout", {})
right = layout.get("right", [])
if not any(isinstance(entry, dict) and entry.get("id") == sys.argv[2] for entry in right):
    raise SystemExit("target widget is not in bar.layout.right")
' "${shell_json}" "${plugin_id}"
}

write_record() {
  printf '%s\n' "$2" >"${record_dir}/$1"
}

shell_ping() {
  [[ "$(omarchy-shell shell ping)" == "ok" ]] || fail "shell ping did not return ok"
}

helper_count() {
  { pgrep -af "${target_plugin}/helper/opatchy.py" || true; } | wc -l
}

monitor_helpers() {
  local parent_pid="$1"
  while :; do
    if (( $(helper_count) > 1 )); then
      printf 'more than one Opatchy helper observed\n' >"${record_dir}/helper-violation.txt"
      kill -TERM "${parent_pid}"
      return
    fi
    sleep 1
  done
}

restore() {
  local status="$?"
  if [[ "${backup_ready}" != true || "${restoring}" == true ]]; then
    exit "${status}"
  fi
  restoring=true
  set +e
  if [[ -n "${monitor_pid}" ]]; then
    kill "${monitor_pid}" 2>/dev/null
    wait "${monitor_pid}" 2>/dev/null
  fi
  cp -a "${record_dir}/backup/shell.json" "${shell_json}"
  rm -rf "${target_plugin}"
  if [[ -d "${record_dir}/backup/plugin" ]]; then
    cp -a "${record_dir}/backup/plugin" "${target_plugin}"
  fi
  omarchy-shell shell rescanPlugins
  omarchy-shell shell reloadConfig
  restored_shell_digest="$(json_digest "${shell_json}")"
  restored_plugin_digest="$(plugin_digest "${target_plugin}")" || status=1
  [[ "${restored_shell_digest}" == "$(<"${record_dir}/shell.json.sha256")" ]] || status=1
  [[ "${restored_plugin_digest}" == "$(<"${record_dir}/plugin.sha256")" ]] || status=1
  config_contains_ids "${retained_ids[@]}" || status=1
  [[ "$(omarchy-shell shell ping)" == "ok" ]] || status=1
  printf 'restoration_status=%s\n' "${status}" >"${record_dir}/restoration.status"
  exit "${status}"
}

while (( "$#" > 0 )); do
  case "$1" in
    --host) host="${2:-}"; shift 2 ;;
    --approval) approval="${2:-}"; shift 2 ;;
    --plugin-source) plugin_source="${2:-}"; shift 2 ;;
    --record-dir) record_dir="${2:-}"; shift 2 ;;
    --execute) execute=true; shift ;;
    --help) usage; exit 0 ;;
    *) usage >&2; fail "unknown argument: $1" ;;
  esac
done

[[ "${host}" == "tomarchy" || "${host}" == "gomarchy" ]] || fail "host must be tomarchy or gomarchy"
[[ -n "${approval}" ]] || fail "an explicit approved-window identifier is required"
[[ "${approval}" == "todo27-${host}-"* ]] || fail "approval identifier must be bound to the selected host"
[[ "${execute}" == true ]] || fail "refusing to mutate without --execute"
[[ "${plugin_source}" == /* && -d "${plugin_source}" ]] || fail "plugin source must be an absolute directory"
[[ "${record_dir}" == /* ]] || fail "record directory must be an absolute private path"
[[ ! -e "${record_dir}" ]] || fail "record directory already exists: ${record_dir}"

readonly shell_json="${HOME}/.config/omarchy/shell.json"
readonly target_plugin="${HOME}/.config/omarchy/plugins/${plugin_id}"
[[ "$(hostname --static)" == "${host}" ]] || fail "selected host does not match this machine"
[[ -f "${shell_json}" ]] || fail "shell.json is required before this QA window"
[[ -f "${plugin_source}/manifest.json" ]] || fail "plugin source has no manifest.json"
[[ "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["id"])' "${plugin_source}/manifest.json")" == "${plugin_id}" ]] || fail "plugin source manifest id is not ${plugin_id}"
find "${plugin_source}" -type l -print -quit | grep -q . && fail "plugin source contains a symlink"

shell_ping
omarchy plugin validate "${plugin_source}" >/dev/null
config_contains_ids "${retained_ids[@]}" || fail "retained plugin inventory prerequisite failed"

mkdir -p "${record_dir}/backup"
cp -a "${shell_json}" "${record_dir}/backup/shell.json"
if [[ -d "${target_plugin}" ]]; then
  cp -a "${target_plugin}" "${record_dir}/backup/plugin"
fi
original_shell_digest="$(json_digest "${shell_json}")"
original_plugin_digest="$(plugin_digest "${target_plugin}")" || fail "target plugin directory is not backup-safe"
write_record "shell.json.sha256" "${original_shell_digest}"
write_record "plugin.sha256" "${original_plugin_digest}"
write_record "window.txt" "host=${host}\napproval=${approval}\nmode=read-only-except-install-enable-restore"
backup_ready=true

trap restore EXIT HUP INT TERM

rm -rf "${target_plugin}"
cp -a "${plugin_source}" "${target_plugin}"
mutated=true
omarchy plugin validate "${target_plugin}" >/dev/null
omarchy-shell shell rescanPlugins
omarchy plugin enable "${plugin_id}"
omarchy bar move "${plugin_id}" --section right
target_is_right_widget
omarchy-shell shell listPlugins >"${record_dir}/plugins.after-enable.json"
grep -Fq "${plugin_id}" "${record_dir}/plugins.after-enable.json" || fail "target plugin was not discovered after enable"
shell_ping

helper_count="$(helper_count)"
[[ "${helper_count}" -le 1 ]] || fail "more than one Opatchy helper observed"
write_record "helper-count.txt" "${helper_count}"
write_record "handoff-policy.txt" "The QA runner invokes no update handoff command and the checklist forbids activating any update-terminal control."
monitor_helpers "$$" &
monitor_pid="$!"
printf 'READY: complete only the read-only scan, refresh, panel keyboard, and pointer checks in the test packet; do not activate update actions.\n'
while :; do
  IFS= read -r -p 'Type RESTORE when the read-only checks are complete: ' response || fail "QA window ended without restoration confirmation"
  [[ "${response}" == "RESTORE" ]] && break
  printf 'Waiting for RESTORE; update handoff remains prohibited.\n'
done
