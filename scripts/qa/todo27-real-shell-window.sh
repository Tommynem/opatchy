#!/usr/bin/env bash
set -euo pipefail

readonly plugin_id="io.github.tomge.opatchy"
readonly hostname_bin="/usr/bin/hostname"
readonly discovery_attempts=50
readonly discovery_poll_seconds=0.1
readonly -a retained_ids=(
  "akitaonrails.ai-usagebar"
  "io.github.sirjul1337.lock-explorer"
  "mirador"
  "omaplug"
  "jkoestinger.vpn"
)

host=""
window_id=""
approval=""
plugin_source=""
record_dir=""
execute=false
backup_ready=false
restoring=false
monitor_pid=""
trap_status=0
signal_status=0
original_helper_count=""

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage:
  todo27-real-shell-window.sh --host tomarchy|gomarchy \
    --window-id YYYYMMDDTHHMMZ \
    --approval todo27:<host>:<window-id> \
    --plugin-source /absolute/path/to/opatchy \
    --record-dir /absolute/private/path --execute

This later-window runner changes only the local host selected by the user. It never
opens an update handoff. Do not run it until that host has an explicit, scheduled
approval window. The approval identifier is structurally bound to the exact host and
scheduled UTC window, and the runner restores the prior shell config and target
plugin state on every exit after a mutation begins.
EOF
}

require_no_symlink_components() {
  local path="$1" current="/" component
  [[ "${path}" == /* ]] || fail "path must be absolute: ${path}"
  IFS=/ read -r -a components <<<"${path#/}"
  for component in "${components[@]}"; do
    [[ -n "${component}" ]] || continue
    current="${current%/}/${component}"
    [[ ! -L "${current}" ]] || fail "symlink path component is not allowed: ${current}"
  done
}

json_digest() {
  python3 -c 'import hashlib,json,sys; print(hashlib.sha256(json.dumps(json.load(sys.stdin), sort_keys=True, separators=(",", ":")).encode()).hexdigest())' <"$1"
}

file_digest() {
  sha256sum "$1" | cut -d' ' -f1
}

plugin_digest() {
  python3 - "$1" <<'PY'
import hashlib
import os
import stat
import sys

root = sys.argv[1]
if not os.path.lexists(root):
    print("absent")
    raise SystemExit(0)

root_stat = os.lstat(root)
if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
    raise SystemExit(f"unsafe plugin root: {root}")

digest = hashlib.sha256()
for current, directories, files in os.walk(root, followlinks=False):
    directories.sort()
    files.sort()
    for name in directories + files:
        path = os.path.join(current, name)
        item = os.lstat(path)
        relative = os.path.relpath(path, root).encode("utf-8", "surrogateescape")
        if stat.S_ISLNK(item.st_mode):
            raise SystemExit(f"symlink found in plugin tree: {path}")
        if stat.S_ISDIR(item.st_mode):
            kind = b"directory"
        elif stat.S_ISREG(item.st_mode):
            kind = b"file"
        else:
            raise SystemExit(f"unsupported plugin tree entry: {path}")
        digest.update(kind + b"\0" + relative + b"\0")
        digest.update(f"{stat.S_IMODE(item.st_mode):04o}".encode() + b"\0")
        if stat.S_ISREG(item.st_mode):
            with open(path, "rb") as source:
                for chunk in iter(lambda: source.read(65536), b""):
                    digest.update(chunk)
print(digest.hexdigest())
PY
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

shell_ipc() {
  omarchy shell shell "$@"
}

shell_ping() {
  [[ "$(shell_ipc ping)" == "ok" ]]
}

plugin_is_discovered() {
  local plugins
  plugins="$(shell_ipc listPlugins)" || return 2
  python3 -c '
import json
import sys

try:
    plugins = json.load(sys.stdin)
except json.JSONDecodeError:
    raise SystemExit(2)
if not isinstance(plugins, list):
    raise SystemExit(2)
raise SystemExit(0 if any(isinstance(plugin, dict) and plugin.get("id") == sys.argv[1] for plugin in plugins) else 1)
' "${plugin_id}" <<<"${plugins}"
}

wait_for_plugin_discovery() {
  local attempt status
  for ((attempt = 1; attempt <= discovery_attempts; attempt++)); do
    if plugin_is_discovered; then
      return
    else
      status="$?"
    fi
    (( status == 1 )) || fail "plugin discovery query failed after rescan"
    (( attempt == discovery_attempts )) || sleep "${discovery_poll_seconds}"
  done
  fail "plugin ${plugin_id} was not discovered within 5 seconds after rescan"
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

stop_monitor() {
  if [[ -n "${monitor_pid}" ]]; then
    kill "${monitor_pid}" 2>/dev/null || true
    wait "${monitor_pid}" 2>/dev/null || true
    printf 'stopped\n' >"${record_dir}/helper-monitor.status"
    monitor_pid=""
  fi
}

restore() {
  trap_status="$?"
  local original_status="${trap_status}" restore_status=0 restored_shell_digest restored_file_digest restored_plugin_digest
  (( signal_status == 0 )) || original_status="${signal_status}"
  trap - ERR EXIT HUP INT TERM
  if [[ "${backup_ready}" != true || "${restoring}" == true ]]; then
    exit "${original_status}"
  fi
  restoring=true
  set +e
  stop_monitor
  require_no_symlink_components "${shell_json}"
  require_no_symlink_components "${target_plugin}"
  require_no_symlink_components "${record_dir}/backup/shell.json"
  require_no_symlink_components "${record_dir}/backup/plugin"
  cp -a "${record_dir}/backup/shell.json" "${shell_json}" || restore_status=1
  rm -rf -- "${target_plugin}" || restore_status=1
  if [[ -d "${record_dir}/backup/plugin" ]]; then
    cp -a "${record_dir}/backup/plugin" "${target_plugin}" || restore_status=1
  fi
  shell_ipc rescanPlugins || restore_status=1
  shell_ipc reloadConfig || restore_status=1
  restored_shell_digest="$(json_digest "${shell_json}")" || restore_status=1
  restored_file_digest="$(file_digest "${shell_json}")" || restore_status=1
  restored_plugin_digest="$(plugin_digest "${target_plugin}")" || restore_status=1
  [[ "${restored_shell_digest}" == "$(<"${record_dir}/shell.json.semantic.sha256")" ]] || restore_status=1
  [[ "${restored_file_digest}" == "$(<"${record_dir}/shell.json.bytes.sha256")" ]] || restore_status=1
  [[ "${restored_plugin_digest}" == "$(<"${record_dir}/plugin.sha256")" ]] || restore_status=1
  config_contains_ids "${retained_ids[@]}" || restore_status=1
  shell_ping || restore_status=1
  restored_helper_count="$(helper_count)" || restore_status=1
  write_record "helper-count.after.txt" "${restored_helper_count}"
  [[ "${restored_helper_count}" == "${original_helper_count}" ]] || restore_status=1
  [[ "${original_plugin_digest}" != absent || "${restored_helper_count}" == 0 ]] || restore_status=1
  printf 'restoration_status=%s\noriginal_status=%s\n' "${restore_status}" "${original_status}" >"${record_dir}/restoration.status"
  (( restore_status == 0 )) || exit "${restore_status}"
  exit "${original_status}"
}

while (( "$#" > 0 )); do
  case "$1" in
    --host) host="${2:-}"; shift 2 ;;
    --window-id) window_id="${2:-}"; shift 2 ;;
    --approval) approval="${2:-}"; shift 2 ;;
    --plugin-source) plugin_source="${2:-}"; shift 2 ;;
    --record-dir) record_dir="${2:-}"; shift 2 ;;
    --execute) execute=true; shift ;;
    --help) usage; exit 0 ;;
    *) usage >&2; fail "unknown argument: $1" ;;
  esac
done

[[ "${host}" == "tomarchy" || "${host}" == "gomarchy" ]] || fail "host must be exactly tomarchy or gomarchy"
[[ "${window_id}" =~ ^[0-9]{8}T[0-9]{4}Z$ ]] || fail "window id must be scheduled UTC as YYYYMMDDTHHMMZ"
[[ "${approval}" == "todo27:${host}:${window_id}" ]] || fail "approval identifier must exactly bind the selected host and window"
[[ "${execute}" == true ]] || fail "refusing to mutate without --execute"
[[ "${plugin_source}" == /* && -d "${plugin_source}" ]] || fail "plugin source must be an absolute directory"
[[ "${record_dir}" == /* && "${record_dir}" != / ]] || fail "record directory must be a non-root absolute private path"
[[ ! -e "${record_dir}" ]] || fail "record directory already exists: ${record_dir}"

readonly shell_json="${HOME}/.config/omarchy/shell.json"
readonly target_plugin="${HOME}/.config/omarchy/plugins/${plugin_id}"
readonly plugin_parent="${HOME}/.config/omarchy/plugins"
require_no_symlink_components "${HOME}"
require_no_symlink_components "${plugin_source}"
require_no_symlink_components "${record_dir}"
require_no_symlink_components "${shell_json}"
require_no_symlink_components "${plugin_parent}"
require_no_symlink_components "${target_plugin}"
[[ "$("${hostname_bin}")" == "${host}" ]] || fail "selected host does not match this machine"
[[ -f "${shell_json}" && ! -L "${shell_json}" ]] || fail "shell.json must be a regular file"
[[ -d "${plugin_parent}" ]] || fail "plugin directory is required before this QA window"
[[ -f "${plugin_source}/manifest.json" && ! -L "${plugin_source}/manifest.json" ]] || fail "plugin source has no regular manifest.json"
[[ "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["id"])' "${plugin_source}/manifest.json")" == "${plugin_id}" ]] || fail "plugin source manifest id is not ${plugin_id}"
plugin_digest "${plugin_source}" >/dev/null || fail "plugin source contains an unsafe tree entry"
plugin_digest "${target_plugin}" >/dev/null || fail "target plugin directory is not backup-safe"

shell_ping || fail "shell ping did not return ok"
omarchy plugin validate "${plugin_source}" >/dev/null
config_contains_ids "${retained_ids[@]}" || fail "retained plugin inventory prerequisite failed"
original_helper_count="$(helper_count)"
[[ "${original_helper_count}" -le 1 ]] || fail "more than one Opatchy helper observed before mutation"

umask 077
mkdir -m 700 "${record_dir}"
trap restore EXIT ERR
mkdir "${record_dir}/backup"
cp -a "${shell_json}" "${record_dir}/backup/shell.json"
if [[ -d "${target_plugin}" ]]; then
  cp -a "${target_plugin}" "${record_dir}/backup/plugin"
fi
original_shell_digest="$(json_digest "${shell_json}")"
original_file_digest="$(file_digest "${shell_json}")"
original_plugin_digest="$(plugin_digest "${target_plugin}")" || fail "target plugin directory is not backup-safe"
write_record "shell.json.semantic.sha256" "${original_shell_digest}"
write_record "shell.json.bytes.sha256" "${original_file_digest}"
write_record "plugin.sha256" "${original_plugin_digest}"
write_record "helper-count.before.txt" "${original_helper_count}"
printf 'host=%s\nwindow_id=%s\napproval=%s\nmode=read-only-except-install-enable-restore\n' "${host}" "${window_id}" "${approval}" >"${record_dir}/window.txt"
backup_ready=true

trap 'signal_status=129; exit 129' HUP
trap 'signal_status=130; exit 130' INT
trap 'signal_status=143; exit 143' TERM

rm -rf -- "${target_plugin}"
cp -a "${plugin_source}" "${target_plugin}"
omarchy plugin validate "${target_plugin}" >/dev/null
shell_ipc rescanPlugins
wait_for_plugin_discovery
omarchy plugin enable "${plugin_id}"
omarchy bar move "${plugin_id}" --section right
target_is_right_widget
shell_ipc listPlugins >"${record_dir}/plugins.after-enable.json"
grep -Fq "${plugin_id}" "${record_dir}/plugins.after-enable.json" || fail "target plugin was not discovered after enable"
shell_ping

current_helper_count="$(helper_count)"
[[ "${current_helper_count}" -le 1 ]] || fail "more than one Opatchy helper observed"
write_record "helper-count.during.txt" "${current_helper_count}"
write_record "handoff-policy.txt" "The QA runner invokes no update handoff command and the checklist forbids activating any update-terminal control."
monitor_helpers "$$" &
monitor_pid="$!"
printf 'READY: complete only the read-only scan, refresh, panel keyboard, and pointer checks in the test packet; do not activate update actions.\n'
while :; do
  IFS= read -r -p 'Type RESTORE when the read-only checks are complete: ' response || fail "QA window ended without restoration confirmation"
  [[ "${response}" == "RESTORE" ]] && break
  printf 'Waiting for RESTORE; update handoff remains prohibited.\n'
done
