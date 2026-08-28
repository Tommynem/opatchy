#!/usr/bin/env bash
set -euo pipefail

readonly root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly stage="$(mktemp -d)"
readonly -a previews=(
  "${root}/preview.png"
  "${root}/docs/screenshots/fixture-clear.png"
  "${root}/docs/screenshots/fixture-updates.png"
  "${root}/docs/screenshots/fixture-security-stale.png"
  "${root}/docs/screenshots/fixture-transparent-stale.png"
)

cleanup() {
  rm -rf "${stage}"
}
trap cleanup EXIT

bash "${root}/scripts/qa/capture_todo27_fixture_preview.sh" >/dev/null
sha256sum "${previews[@]}" >"${stage}/first.sha256"
bash "${root}/scripts/qa/capture_todo27_fixture_preview.sh" >/dev/null
sha256sum "${previews[@]}" >"${stage}/second.sha256"
cmp "${stage}/first.sha256" "${stage}/second.sha256"
! rg -n '/home/|/Users/|/private/|package inventory|real host capture' "${root}/.omo/evidence/task-24-opatchy/visual-qa/context/context.sha256"
grep -Fq 'ILLUSTRATIVE FIXTURE DATA' "${root}/scripts/qa/capture_todo27_fixture_preview.sh"
printf '%s\n' 'PASS: Todo 27 fixture previews regenerate deterministically without private source paths'
