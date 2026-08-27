#!/usr/bin/env bash
set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly capture_root="${OPATCHY_CAPTURE_ROOT:-${repository_root}}"
readonly evidence_root="${capture_root}/.omo/evidence/task-24-opatchy/visual-qa"
readonly output_directory="${evidence_root}/png"
readonly manifest="${evidence_root}/matrix.tsv"
readonly generation_manifest="${evidence_root}/generation.sha256"
readonly -a states=(security watched updates degraded clear)
readonly -a themes=(light dark contrast transparent)
readonly -a layouts=(horizontal vertical narrow)

fail() { printf '%s\n' "$1" >&2; exit 1; }

geometry_for() {
    case "$1" in
        horizontal) printf '%s' '192x56' ;;
        vertical) printf '%s' '56x192' ;;
        narrow) printf '%s' '88x56' ;;
    esac
}

index_of() {
    local value="$1"
    shift
    local index=0
    for candidate in "$@"; do
        [[ "${candidate}" == "${value}" ]] && { printf '%s' "${index}"; return; }
        (( index += 1 ))
    done
    fail "unknown matrix value: ${value}"
}

expected_code() {
    local state="$1" theme="$2" layout="$3" code
    code=$(( $(index_of "${state}" "${states[@]}") + 1 + $(index_of "${theme}" "${themes[@]}") * 8 + $(index_of "${layout}" "${layouts[@]}") * 32 ))
    [[ "${state}-${theme}-${layout}" == 'security-dark-horizontal' ]] && code=$(( code + 128 + 256 ))
    printf '%s' "${code}"
}

pixel_bit() {
    local image="$1" bit="$2" pixel
    pixel="$(identify -format "%[pixel:p{$((2 + bit * 3)),2}]" "${image}")"
    [[ "${pixel}" == 'srgba(255,0,255,1)' ]] && { printf '%s' 1; return; }
    [[ "${pixel}" == 'srgba(0,255,255,1)' ]] && { printf '%s' 0; return; }
    fail "invalid semantic signature pixel ${bit}: ${image} (${pixel})"
}

verify_generation() {
    [[ -f "${generation_manifest}" ]] || fail "missing generation manifest: ${generation_manifest}"
    [[ "$(sed -n '1p' "${generation_manifest}")" == "generation_id=${OPATCHY_CAPTURE_GENERATION:-}" ]] || fail 'generation identity does not match this capture run'
    tail -n +2 "${generation_manifest}" | sha256sum -c - >/dev/null || fail 'source hash manifest is invalid'
}

verify_generation
printf 'state\ttheme\tlayout\tpath\tgeometry\n' >"${manifest}"
expected=0
for state in "${states[@]}"; do
    for theme in "${themes[@]}"; do
        for layout in "${layouts[@]}"; do
            (( expected += 1 ))
            image="${output_directory}/${state}-${theme}-${layout}.png"
            [[ -f "${image}" ]] || fail "missing capture: ${image}"
            [[ "$(file -b --mime-type "${image}")" == 'image/png' ]] || fail "invalid PNG signature: ${image}"
            [[ "$(identify -format '%wx%h %[channels]' "${image}")" == "$(geometry_for "${layout}") srgba"* ]] || fail "invalid geometry or alpha: ${image}"
            [[ "$(magick "${image}" -alpha extract -format '%[fx:maxima]' info:)" != '0' ]] || fail "blank alpha: ${image}"
            if [[ "${theme}" == 'transparent' ]]; then
                [[ "$(magick "${image}" -alpha extract -format '%[fx:minima]' info:)" == '0' ]] || fail "transparent theme lacks transparent pixels: ${image}"
            fi
            code="$(expected_code "${state}" "${theme}" "${layout}")"
            actual_code=0
            for bit in {0..9}; do
                : $(( actual_code += $(pixel_bit "${image}" "${bit}") << bit ))
            done
            [[ "${actual_code}" -eq "${code}" ]] || fail "semantic signature mismatch: ${image} expected ${code}, got ${actual_code}"
            printf '%s\t%s\t%s\tpng/%s-%s-%s.png\t%s\n' "${state}" "${theme}" "${layout}" "${state}" "${theme}" "${layout}" "$(geometry_for "${layout}")" >>"${manifest}"
        done
    done
done

actual="$(find "${output_directory}" -maxdepth 1 -type f -name '*.png' | wc -l)"
[[ "${actual}" -eq "${expected}" ]] || fail "expected ${expected} captures, found ${actual}"
printf 'PASS: %s verified captures; manifest: %s\n' "${expected}" "${manifest}"
