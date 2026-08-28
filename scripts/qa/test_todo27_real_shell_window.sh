#!/usr/bin/env bash
set -euo pipefail

readonly root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly runner="${root}/scripts/qa/todo27-real-shell-window.sh"
readonly temporary_root="$(mktemp -d)"
readonly window_id="20260828T1200Z"

cleanup() {
  rm -rf "${temporary_root}"
}
trap cleanup EXIT

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

expect_failure() {
  local expected="$1"
  shift
  local output
  if output="$("$@" 2>&1)"; then
    fail "expected failure: $*"
  fi
  [[ "${output}" == *"${expected}"* ]] || fail "missing failure ${expected}: ${output}"
}

tree_digest() {
  python3 - "$1" <<'PY'
import hashlib
import os
import stat
import sys

root = sys.argv[1]
if not os.path.lexists(root):
    print("absent")
    raise SystemExit(0)
digest = hashlib.sha256()
for current, directories, files in os.walk(root, followlinks=False):
    directories.sort()
    files.sort()
    for name in directories + files:
        path = os.path.join(current, name)
        item = os.lstat(path)
        if stat.S_ISLNK(item.st_mode):
            raise SystemExit("unexpected symlink")
        kind = b"directory" if stat.S_ISDIR(item.st_mode) else b"file"
        relative = os.path.relpath(path, root).encode()
        digest.update(kind + b"\0" + relative + b"\0")
        digest.update(f"{stat.S_IMODE(item.st_mode):04o}".encode() + b"\0")
        if stat.S_ISREG(item.st_mode):
            digest.update(open(path, "rb").read())
print(digest.hexdigest())
PY
}

fixture_root="${temporary_root}/fixture"
home="${fixture_root}/home"
source_plugin="${fixture_root}/source"
fake_bin="${fixture_root}/bin"
command_log="${fixture_root}/command.log"
fixture_runner="${fixture_root}/todo27-real-shell-window.sh"

setup_fixture() {
  rm -rf "${fixture_root}"
  mkdir -p "${home}/.config/omarchy/plugins" "${source_plugin}" "${fake_bin}"
  cp "${root}/manifest.json" "${source_plugin}/manifest.json"
  printf 'Item {}\n' >"${source_plugin}/Service.qml"
  printf '{"version":1,"settings":{"preserve":"unchanged"},"bar":{"layout":{"left":[{"id":"clock"}],"right":[{"id":"akitaonrails.ai-usagebar","setting":"A"},{"id":"io.github.sirjul1337.lock-explorer"},{"id":"mirador"},{"id":"omaplug"},{"id":"jkoestinger.vpn"}]}}}\n' >"${home}/.config/omarchy/shell.json"
  cp "${home}/.config/omarchy/shell.json" "${fixture_root}/original-shell.json"

  cat >"${fake_bin}/omarchy" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf 'omarchy %s\n' "$*" >>"${TODO27_COMMAND_LOG}"
case "$1 $2" in
  "plugin validate")
    if [[ "${FAIL_VALIDATE_TARGET:-0}" == 1 && "$3" == "$HOME/.config/omarchy/plugins/io.github.tomge.opatchy" ]]; then
      printf '%s\n' 'target validation failure' >&2
      exit 1
    fi
    ;;
  "plugin enable")
    if [[ "${DELAY_PLUGIN_DISCOVERY:-0}" == 1 && ! -f "$HOME/plugin-known" ]]; then
      printf "%s\n" "plugin '$3' is not known; run: omarchy-shell shell rescanPlugins" >&2
      exit 1
    fi
    if [[ "${DELAY_PLUGIN_DISCOVERY:-0}" == 1 ]]; then
      cp "$HOME/discovery-list.calls" "$HOME/discovery-list.calls-at-enable"
    fi
    python3 - "$HOME/.config/omarchy/shell.json" "$3" <<'PY'
import json
import sys
path = sys.argv[1]
document = json.load(open(path, encoding="utf-8"))
document["bar"]["layout"]["right"].append({"id": sys.argv[2]})
open(path, "w", encoding="utf-8").write(json.dumps(document))
PY
    touch "$HOME/enabled"
    touch "$HOME/helper-running"
    ;;
  "plugin disable") : ;;
  "bar move") : ;;
  "shell shell")
    case "$3" in
      ping) printf 'ok\n' ;;
      listPlugins)
        if [[ "${DELAY_PLUGIN_DISCOVERY:-0}" == 1 && -f "$HOME/discovery-rescan" ]]; then
          calls=0
          [[ -f "$HOME/discovery-list.calls" ]] && calls="$(<"$HOME/discovery-list.calls")"
          calls=$((calls + 1))
          printf '%s\n' "${calls}" >"$HOME/discovery-list.calls"
          if [[ "${DISCOVERY_NEVER_READY:-0}" != 1 && "${calls}" -ge "${DISCOVERY_DELAY_LIST_CALLS:-3}" ]]; then
            touch "$HOME/plugin-known"
          fi
        fi
        if [[ "${DELAY_PLUGIN_DISCOVERY:-0}" != 1 || -f "$HOME/plugin-known" ]]; then
          printf '%s\n' '[{"id":"io.github.tomge.opatchy"}]'
        else
          printf '%s\n' '[]'
        fi
        ;;
      rescanPlugins)
        if [[ "${DELAY_PLUGIN_DISCOVERY:-0}" == 1 ]]; then
          rm -f "$HOME/plugin-known" "$HOME/discovery-list.calls"
          touch "$HOME/discovery-rescan"
        fi
        ;;
      reloadConfig)
        if [[ "${PERSIST_HELPER_AFTER_RESTORE:-0}" == 1 ]]; then
          touch "$HOME/helper-running"
        elif grep -Fq 'io.github.tomge.opatchy' "$HOME/.config/omarchy/shell.json" && [[ -d "$HOME/.config/omarchy/plugins/io.github.tomge.opatchy" ]]; then
          touch "$HOME/helper-running"
        else
          rm -f "$HOME/helper-running"
        fi
        ;;
      *) exit 1 ;;
    esac
    ;;
  *) exit 1 ;;
esac
EOF
  cat >"${fake_bin}/pgrep" <<'EOF'
#!/usr/bin/env bash
if [[ -f "$HOME/helper-running" ]]; then
  printf '%s\n' "123 $HOME/.config/omarchy/plugins/io.github.tomge.opatchy/helper/opatchy.py"
  exit 0
fi
exit 1
EOF
  cat >"${fake_bin}/hostname" <<'EOF'
#!/usr/bin/env bash
printf 'hostname argc=%s args=%s\n' "$#" "$*" >>"${TODO27_COMMAND_LOG}"
if (( "$#" != 0 )); then
  printf '%s\n' "hostname: unrecognized option '$1'" >&2
  exit 64
fi
printf '%s\n' "${FAKE_HOST:-tomarchy}"
EOF
  cat >"${fake_bin}/cp" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${FAIL_COPY_SOURCE:-0}" == 1 && "$2" == "${TODO27_SOURCE_PLUGIN}" ]]; then
  mkdir -p "$3"
  printf 'partial install\n' >"$3/partial.txt"
  printf '%s\n' 'partial install failure' >&2
  exit 1
fi
if [[ "${FAIL_COPY_BACKUP:-0}" == 1 && "$2" == "$HOME/.config/omarchy/plugins/io.github.tomge.opatchy" ]]; then
  printf '%s\n' 'backup copy failure' >&2
  exit 1
fi
if [[ "${DISALLOW_WATCHED_COPY:-0}" == 1 && "$2" == "${TODO27_SOURCE_PLUGIN}" && "$3" == "$HOME/.config/omarchy/plugins/io.github.tomge.opatchy" ]]; then
  printf '%s\n' 'source copy must not write directly into the watched plugin directory' >&2
  exit 1
fi
command -p cp "$@"
EOF
  chmod +x "${fake_bin}/omarchy" "${fake_bin}/pgrep" "${fake_bin}/hostname" "${fake_bin}/cp"
  python3 - "${runner}" "${fixture_runner}" "${fake_bin}/hostname" <<'PY'
import sys

source, target, hostname = sys.argv[1:]
text = open(source, encoding="utf-8").read()
needle = 'readonly hostname_bin="/usr/bin/hostname"'
replacement = f'readonly hostname_bin="{hostname}"'
assert needle in text
open(target, "w", encoding="utf-8").write(text.replace(needle, replacement, 1))
PY
  chmod +x "${fixture_runner}"
  : >"${command_log}"
}

run_runner() {
  local record_dir="$1"
  shift
  HOME="${home}" PATH="${fake_bin}:${PATH}" TODO27_COMMAND_LOG="${command_log}" TODO27_SOURCE_PLUGIN="${source_plugin}" "$@" \
    bash "${fixture_runner}" --host tomarchy --window-id "${window_id}" --approval "todo27:tomarchy:${window_id}" \
      --plugin-source "${source_plugin}" --record-dir "${record_dir}" --execute
}

assert_restored() {
  local record_dir="$1" expected_plugin="$2" expected_helpers="$3"
  cmp "${fixture_root}/original-shell.json" "${home}/.config/omarchy/shell.json"
  [[ "$(tree_digest "${home}/.config/omarchy/plugins/io.github.tomge.opatchy")" == "${expected_plugin}" ]] || fail "plugin tree was not restored"
  grep -Fxq 'restoration_status=0' "${record_dir}/restoration.status"
  [[ "$(<"${record_dir}/helper-count.before.txt")" == "${expected_helpers}" ]]
  [[ "$(<"${record_dir}/helper-count.after.txt")" == "${expected_helpers}" ]]
  grep -Fq 'akitaonrails.ai-usagebar' "${home}/.config/omarchy/shell.json"
  grep -Fq 'jkoestinger.vpn' "${home}/.config/omarchy/shell.json"
}

setup_fixture
expect_failure 'refusing to mutate without --execute' env HOME="${home}" PATH="${fake_bin}:${PATH}" TODO27_COMMAND_LOG="${command_log}" \
  bash "${fixture_runner}" --host tomarchy --window-id "${window_id}" --approval "todo27:tomarchy:${window_id}" --plugin-source "${source_plugin}" --record-dir "${fixture_root}/default-deny"
[[ ! -e "${fixture_root}/default-deny" ]]

setup_fixture
expect_failure 'approval identifier must exactly bind' env HOME="${home}" PATH="${fake_bin}:${PATH}" TODO27_COMMAND_LOG="${command_log}" \
  bash "${fixture_runner}" --host tomarchy --window-id "${window_id}" --approval 'todo27:tomarchy:20260828T1300Z' --plugin-source "${source_plugin}" --record-dir "${fixture_root}/wrong-window" --execute
expect_failure 'selected host does not match' env FAKE_HOST=gomarchy HOME="${home}" PATH="${fake_bin}:${PATH}" TODO27_COMMAND_LOG="${command_log}" \
  bash "${fixture_runner}" --host tomarchy --window-id "${window_id}" --approval "todo27:tomarchy:${window_id}" --plugin-source "${source_plugin}" --record-dir "${fixture_root}/wrong-host" --execute

ln -s "${fixture_root}/outside" "${source_plugin}/nested-link"
expect_failure 'plugin source contains an unsafe tree entry' env HOME="${home}" PATH="${fake_bin}:${PATH}" TODO27_COMMAND_LOG="${command_log}" \
  bash "${fixture_runner}" --host tomarchy --window-id "${window_id}" --approval "todo27:tomarchy:${window_id}" --plugin-source "${source_plugin}" --record-dir "${fixture_root}/source-link" --execute
rm "${source_plugin}/nested-link"
ln -s "${fixture_root}/outside" "${home}/.config/omarchy/plugins/io.github.tomge.opatchy"
expect_failure 'symlink path component is not allowed' env HOME="${home}" PATH="${fake_bin}:${PATH}" TODO27_COMMAND_LOG="${command_log}" \
  bash "${fixture_runner}" --host tomarchy --window-id "${window_id}" --approval "todo27:tomarchy:${window_id}" --plugin-source "${source_plugin}" --record-dir "${fixture_root}/target-link" --execute
rm "${home}/.config/omarchy/plugins/io.github.tomge.opatchy"

record_dir="${fixture_root}/absent-record"
printf 'RESTORE\n' | run_runner "${record_dir}" env DISALLOW_WATCHED_COPY=1
[[ "$(<"${record_dir}/helper-count.during.txt")" == 1 ]]
assert_restored "${record_dir}" absent 0
[[ "$(<"${record_dir}/helper-monitor.status")" == stopped ]]

setup_fixture
HOME="${home}" PATH="${fake_bin}:${PATH}" TODO27_COMMAND_LOG="${command_log}" \
  DELAY_PLUGIN_DISCOVERY=1 omarchy shell shell rescanPlugins
expect_failure "plugin 'io.github.tomge.opatchy' is not known" env HOME="${home}" PATH="${fake_bin}:${PATH}" \
  TODO27_COMMAND_LOG="${command_log}" DELAY_PLUGIN_DISCOVERY=1 omarchy plugin enable io.github.tomge.opatchy

setup_fixture
record_dir="${fixture_root}/delayed-discovery-record"
printf 'RESTORE\n' | run_runner "${record_dir}" env DELAY_PLUGIN_DISCOVERY=1 DISCOVERY_DELAY_LIST_CALLS=3
assert_restored "${record_dir}" absent 0
[[ "$(<"${home}/discovery-list.calls-at-enable")" == 3 ]]

setup_fixture
record_dir="${fixture_root}/discovery-timeout-record"
expect_failure 'was not discovered within 5 seconds after rescan' run_runner "${record_dir}" env \
  DELAY_PLUGIN_DISCOVERY=1 DISCOVERY_NEVER_READY=1
assert_restored "${record_dir}" absent 0
! grep -Fq 'plugin enable' "${command_log}"

setup_fixture
target_plugin="${home}/.config/omarchy/plugins/io.github.tomge.opatchy"
mkdir -p "${target_plugin}/empty" "${target_plugin}/nested"
printf 'prior state\n' >"${target_plugin}/nested/retained.txt"
chmod 700 "${target_plugin}/nested/retained.txt"
existing_digest="$(tree_digest "${target_plugin}")"
record_dir="${fixture_root}/existing-record"
printf 'RESTORE\n' | run_runner "${record_dir}" env
assert_restored "${record_dir}" "${existing_digest}" 0
[[ -d "${target_plugin}/empty" && -x "${target_plugin}/nested/retained.txt" ]]

setup_fixture
target_plugin="${home}/.config/omarchy/plugins/io.github.tomge.opatchy"
mkdir -p "${target_plugin}/empty"
printf 'prior state\n' >"${target_plugin}/retained.txt"
existing_digest="$(tree_digest "${target_plugin}")"
record_dir="${fixture_root}/load-failure-record"
expect_failure 'target validation failure' run_runner "${record_dir}" env FAIL_VALIDATE_TARGET=1
assert_restored "${record_dir}" "${existing_digest}" 0

setup_fixture
target_plugin="${home}/.config/omarchy/plugins/io.github.tomge.opatchy"
mkdir -p "${target_plugin}/empty"
printf 'prior state\n' >"${target_plugin}/retained.txt"
existing_digest="$(tree_digest "${target_plugin}")"
record_dir="${fixture_root}/partial-install-record"
expect_failure 'partial install' run_runner "${record_dir}" env FAIL_COPY_SOURCE=1
assert_restored "${record_dir}" "${existing_digest}" 0

setup_fixture
target_plugin="${home}/.config/omarchy/plugins/io.github.tomge.opatchy"
mkdir -p "${target_plugin}"
printf 'prior state\n' >"${target_plugin}/retained.txt"
record_dir="${fixture_root}/partial-backup-record"
expect_failure 'backup copy failure' run_runner "${record_dir}" env FAIL_COPY_BACKUP=1
cmp "${fixture_root}/original-shell.json" "${home}/.config/omarchy/shell.json"
[[ "$(<"${target_plugin}/retained.txt")" == 'prior state' ]]
! grep -Fq 'plugin enable' "${command_log}"

run_interrupted_case() {
  local signal="$1" record_dir fifo output runner_pid expected_plugin
  setup_fixture
  target_plugin="${home}/.config/omarchy/plugins/io.github.tomge.opatchy"
  mkdir -p "${target_plugin}/empty"
  printf 'prior state\n' >"${target_plugin}/retained.txt"
  expected_plugin="$(tree_digest "${target_plugin}")"
  record_dir="${fixture_root}/${signal,,}-record"
  fifo="${fixture_root}/input"
  output="${fixture_root}/runner.out"
  mkfifo "${fifo}"
  HOME="${home}" PATH="${fake_bin}:${PATH}" TODO27_COMMAND_LOG="${command_log}" TODO27_SOURCE_PLUGIN="${source_plugin}" \
    bash "${fixture_runner}" --host tomarchy --window-id "${window_id}" --approval "todo27:tomarchy:${window_id}" --plugin-source "${source_plugin}" --record-dir "${record_dir}" --execute <"${fifo}" >"${output}" 2>&1 &
  runner_pid="$!"
  exec 3>"${fifo}"
  for _ in {1..100}; do
    grep -Fq 'READY:' "${output}" && break
    sleep 0.05
  done
  grep -Fq 'READY:' "${output}" || fail "runner did not reach interrupted read-only state"
  kill -s "${signal}" "${runner_pid}"
  exec 3>&-
  if wait "${runner_pid}"; then
    fail "${signal} interruption unexpectedly succeeded"
  fi
  assert_restored "${record_dir}" "${expected_plugin}" 0
}

run_interrupted_case INT
run_interrupted_case TERM

setup_fixture
target_plugin="${home}/.config/omarchy/plugins/io.github.tomge.opatchy"
mkdir -p "${target_plugin}"
printf 'prior state\n' >"${target_plugin}/retained.txt"
python3 - "${home}/.config/omarchy/shell.json" <<'PY'
import json
import sys

path = sys.argv[1]
document = json.load(open(path, encoding="utf-8"))
document["bar"]["layout"]["right"].append({"id": "io.github.tomge.opatchy"})
open(path, "w", encoding="utf-8").write(json.dumps(document))
PY
cp "${home}/.config/omarchy/shell.json" "${fixture_root}/original-shell.json"
touch "${home}/helper-running"
existing_digest="$(tree_digest "${target_plugin}")"
record_dir="${fixture_root}/active-record"
printf 'RESTORE\n' | run_runner "${record_dir}" env
assert_restored "${record_dir}" "${existing_digest}" 1
[[ "$(<"${record_dir}/helper-count.during.txt")" == 1 ]]

setup_fixture
record_dir="${fixture_root}/persistent-helper-record"
if printf 'RESTORE\n' | run_runner "${record_dir}" env PERSIST_HELPER_AFTER_RESTORE=1; then
  fail 'expected persistent helper restoration to fail'
fi
cmp "${fixture_root}/original-shell.json" "${home}/.config/omarchy/shell.json"
[[ ! -e "${home}/.config/omarchy/plugins/io.github.tomge.opatchy" ]]
grep -Fxq 'restoration_status=1' "${record_dir}/restoration.status"
[[ "$(<"${record_dir}/helper-count.before.txt")" == 0 ]]
[[ "$(<"${record_dir}/helper-count.after.txt")" == 1 ]]

! grep -Eq '(^|[[:space:]])(omarchy[[:space:]]+update|omarchy[[:space:]]+refresh|omarchy[[:space:]]+shell[[:space:]]+update)' "${command_log}"
grep -Fxq 'omarchy shell shell ping' "${command_log}"
grep -Fxq 'hostname argc=0 args=' "${command_log}"
! grep -Fq 'omarchy-shell' "${runner}"
! grep -Fq 'fixture' "${runner}"
printf '%s\n' 'PASS: guarded fake-host cases prove public IPC spelling, exact state restoration, helper lifecycle comparison, and no update handoff'
