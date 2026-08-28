#!/usr/bin/env bash
set -euo pipefail

readonly root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly runner="${root}/scripts/qa/todo27-real-shell-window.sh"
readonly temporary_root="$(mktemp -d)"

cleanup() {
  rm -rf "${temporary_root}"
}
trap cleanup EXIT

home="${temporary_root}/home"
source_plugin="${temporary_root}/source"
record_dir="${temporary_root}/record"
fake_bin="${temporary_root}/bin"
mkdir -p "${home}/.config/omarchy/plugins" "${source_plugin}" "${fake_bin}"
cp "${root}/manifest.json" "${source_plugin}/manifest.json"
printf 'Item {}\n' >"${source_plugin}/Service.qml"
printf '{"version":1,"bar":{"layout":{"right":[{"id":"akitaonrails.ai-usagebar"},{"id":"io.github.sirjul1337.lock-explorer"},{"id":"mirador"},{"id":"omaplug"},{"id":"jkoestinger.vpn"}]}}}\n' >"${home}/.config/omarchy/shell.json"
cp "${home}/.config/omarchy/shell.json" "${temporary_root}/original-shell.json"

cat >"${fake_bin}/omarchy" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "$1 $2" in
  "plugin validate") exit 0 ;;
  "plugin enable")
    python3 - "$HOME/.config/omarchy/shell.json" "$3" <<'PY'
import json
import sys
path = sys.argv[1]
document = json.load(open(path, encoding="utf-8"))
document["bar"]["layout"]["right"].append({"id": sys.argv[2]})
open(path, "w", encoding="utf-8").write(json.dumps(document))
PY
    touch "$HOME/enabled"
    ;;
  "bar move") exit 0 ;;
  *) exit 1 ;;
esac
EOF
cat >"${fake_bin}/omarchy-shell" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "$2" in
  ping) printf 'ok\n' ;;
  listPlugins)
    printf '%s\n' 'akitaonrails.ai-usagebar io.github.sirjul1337.lock-explorer mirador omaplug jkoestinger.vpn'
    [[ -f "$HOME/enabled" ]] && printf '%s\n' 'io.github.tomge.opatchy'
    ;;
  rescanPlugins|reloadConfig) : ;;
  *) exit 1 ;;
esac
EOF
cat >"${fake_bin}/pgrep" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' '123 /temporary/plugin/helper/opatchy.py'
EOF
cat >"${fake_bin}/hostname" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "${FAKE_HOST:-tomarchy}"
EOF
chmod +x "${fake_bin}/omarchy" "${fake_bin}/omarchy-shell" "${fake_bin}/pgrep" "${fake_bin}/hostname"

if HOME="${home}" PATH="${fake_bin}:${PATH}" bash "${runner}" --host tomarchy --approval todo27-tomarchy-fixture-window --plugin-source "${source_plugin}" --record-dir "${record_dir}"; then
  printf '%s\n' 'expected explicit execute guard to fail' >&2
  exit 1
fi
cmp "${temporary_root}/original-shell.json" "${home}/.config/omarchy/shell.json"

if FAKE_HOST=gomarchy HOME="${home}" PATH="${fake_bin}:${PATH}" bash "${runner}" --host tomarchy --approval todo27-tomarchy-fixture-window --plugin-source "${source_plugin}" --record-dir "${temporary_root}/wrong-host-record" --execute; then
  printf '%s\n' 'expected host identity guard to fail' >&2
  exit 1
fi

ln -s "${temporary_root}/target-plugin" "${home}/.config/omarchy/plugins/io.github.tomge.opatchy"
if HOME="${home}" PATH="${fake_bin}:${PATH}" bash "${runner}" --host tomarchy --approval todo27-tomarchy-fixture-window --plugin-source "${source_plugin}" --record-dir "${temporary_root}/symlink-record" --execute; then
  printf '%s\n' 'expected target symlink guard to fail' >&2
  exit 1
fi
[[ -L "${home}/.config/omarchy/plugins/io.github.tomge.opatchy" ]]
rm "${home}/.config/omarchy/plugins/io.github.tomge.opatchy"

printf 'RESTORE\n' | HOME="${home}" PATH="${fake_bin}:${PATH}" bash "${runner}" --host tomarchy --approval todo27-tomarchy-fixture-window --plugin-source "${source_plugin}" --record-dir "${record_dir}" --execute
cmp "${temporary_root}/original-shell.json" "${home}/.config/omarchy/shell.json"
[[ ! -e "${home}/.config/omarchy/plugins/io.github.tomge.opatchy" ]]
[[ "$(<"${record_dir}/restoration.status")" == 'restoration_status=0' ]]
[[ "$(<"${record_dir}/helper-count.txt")" == '1' ]]
grep -Fq 'no update handoff command' "${record_dir}/handoff-policy.txt"
printf '%s\n' 'PASS: guarded window fixture restores shell and target plugin state without update handoff'
