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

signature_pixels() {
    local image="$1" width="$2" height="$3" format='' pixel
    for pixel in {0..4}; do
        format+="%[pixel:p{$((width - 1 - pixel)),$((height - 1))}]|"
    done
    identify -format "${format}" "${image}"
}

expected_label() {
    case "$1-$2-$3" in
        security-dark-horizontal) printf '%s' '!1 ~ …' ;;
        security-*) printf '%s' '!1' ;;
        watched-*) printf '%s' '*2' ;;
        updates-*) printf '%s' '^4' ;;
        degraded-*) printf '%s' '?1' ;;
        clear-*) printf '%s' 'O' ;;
    esac
}

label_bit() {
    local label="$1" bit="$2" character character_bit code
    if (( bit < 8 )); then
        (( ${#label} & (1 << bit) )) && printf '%s' 1 || printf '%s' 0
        return
    fi
    character=$(( (bit - 8) / 16 ))
    character_bit=$(( (bit - 8) % 16 ))
    [[ "${character}" -lt "${#label}" ]] || { printf '%s' 0; return; }
    case "${label:character:1}" in
        '…') code=8230 ;;
        *) printf -v code '%d' "'${label:character:1}" ;;
    esac
    (( code & (1 << character_bit) )) && printf '%s' 1 || printf '%s' 0
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
            label="$(expected_label "${state}" "${theme}" "${layout}")"
            geometry="$(geometry_for "${layout}")"
            width="${geometry%x*}"
            height="${geometry#*x}"
            IFS='|' read -r -a pixels <<<"$(signature_pixels "${image}" "${width}" "${height}")"
            for bit in {0..113}; do
                expected_bit=$(( bit < 10 ? (code >> bit) & 1 : $(label_bit "${label}" "$((bit - 10))") ))
                byte=$(( bit / 8 ))
                channel=$(( byte % 3 + 1 ))
                [[ "${pixels[byte / 3]}" =~ ^srgba\(([0-9]+),([0-9]+),([0-9]+),1\)$ ]] || fail "invalid packed signature pixel: ${image} (${pixels[byte / 3]})"
                actual_bit=$(( (BASH_REMATCH[channel] >> (bit % 8)) & 1 ))
                [[ "${actual_bit}" -eq "${expected_bit}" ]] || {
                    (( bit >= 10 )) && fail "label signature mismatch: ${image} expected ${label}" || fail "semantic signature mismatch: ${image} expected ${code}"
                }
            done
            printf '%s\t%s\t%s\tpng/%s-%s-%s.png\t%s\n' "${state}" "${theme}" "${layout}" "${state}" "${theme}" "${layout}" "$(geometry_for "${layout}")" >>"${manifest}"
        done
    done
done

actual="$(find "${output_directory}" -maxdepth 1 -type f -name '*.png' | wc -l)"
[[ "${actual}" -eq "${expected}" ]] || fail "expected ${expected} captures, found ${actual}"
printf 'PASS: %s verified captures; manifest: %s\n' "${expected}" "${manifest}"
