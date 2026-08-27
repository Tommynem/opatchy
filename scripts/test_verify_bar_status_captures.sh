#!/usr/bin/env bash
set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly evidence_root="${repository_root}/.omo/evidence/task-24-opatchy/visual-qa"
readonly output_directory="${evidence_root}/png"

generation_id() {
    cut -d= -f2 <"${evidence_root}/generation.sha256" | head -n 1
}

expect_failure() {
    local expected="$1"
    shift
    local output
    if output="$("$@" 2>&1)"; then
        printf 'expected failure: %s\n' "$*" >&2
        exit 1
    fi
    [[ "${output}" == *"${expected}"* ]] || { printf 'missing failure %s: %s\n' "${expected}" "${output}" >&2; exit 1; }
}

verify() {
    OPATCHY_CAPTURE_GENERATION="$(generation_id)" bash "${repository_root}/scripts/verify_bar_status_captures.sh"
}

flip_signature_bit() {
    local image="$1" width="$2" height="$3" bit="$4" byte channel x pixel
    byte=$(( bit / 8 ))
    channel=$(( byte % 3 ))
    x=$(( width / 2 + byte / 3 ))
    pixel="$(identify -format "%[pixel:p{${x},$((height - 1))}]" "${image}")"
    [[ "${pixel}" =~ ^srgba\(([0-9]+),([0-9]+),([0-9]+),1\)$ ]] || {
        printf 'invalid packed signature pixel: %s (%s)\n' "${image}" "${pixel}" >&2
        exit 1
    }
    local -a channels=("${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}")
    channels[channel]=$(( channels[channel] ^ (1 << (bit % 8)) ))
    magick "${image}" -fill "srgba(${channels[0]},${channels[1]},${channels[2]},1)" \
        -draw "point ${x},$((height - 1))" "PNG32:${image}"
}

bash "${repository_root}/scripts/capture_bar_status.sh"
magick "${output_directory}/clear-transparent-horizontal.png" -alpha on -channel A -evaluate set 100% +channel "PNG32:${output_directory}/clear-transparent-horizontal.png"
expect_failure 'transparent theme lacks transparent pixels' verify

bash "${repository_root}/scripts/capture_bar_status.sh"
magick -size 192x56 xc:black "PNG32:${output_directory}/updates-dark-horizontal.png"
expect_failure 'semantic signature mismatch' verify

bash "${repository_root}/scripts/capture_bar_status.sh"
cp "${output_directory}/security-light-horizontal.png" "${output_directory}/security-dark-horizontal.png"
expect_failure 'semantic signature mismatch' verify

bash "${repository_root}/scripts/capture_bar_status.sh"
flip_signature_bit "${output_directory}/security-dark-horizontal.png" 192 56 10
expect_failure 'label signature mismatch' verify

bash "${repository_root}/scripts/capture_bar_status.sh"
flip_signature_bit "${output_directory}/security-light-horizontal.png" 192 56 114
expect_failure 'glyph signature mismatch' verify

bash "${repository_root}/scripts/capture_bar_status.sh"
flip_signature_bit "${output_directory}/security-light-horizontal.png" 192 56 135
flip_signature_bit "${output_directory}/security-light-horizontal.png" 192 56 136
expect_failure 'badge signature mismatch' verify

expect_failure 'generation identity does not match this capture run' env OPATCHY_CAPTURE_GENERATION=stale bash "${repository_root}/scripts/verify_bar_status_captures.sh"
bash "${repository_root}/scripts/capture_bar_status.sh"
verify
printf '%s\n' 'PASS: verifier rejects opaque, blank, substituted, wrong-label, wrong-glyph, wrong-badge, and stale artifacts'
