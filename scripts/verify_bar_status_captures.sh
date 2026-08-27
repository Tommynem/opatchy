#!/usr/bin/env bash
set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly evidence_root="${repository_root}/.omo/evidence/task-24-opatchy/visual-qa"
readonly output_directory="${evidence_root}/png"
readonly manifest="${evidence_root}/matrix.tsv"
readonly -a states=(security watched updates degraded clear)
readonly -a themes=(light dark contrast transparent)
readonly -a layouts=(horizontal vertical narrow)

geometry_for() {
    case "$1" in
        horizontal) printf '%s' '192x56' ;;
        vertical) printf '%s' '56x192' ;;
        narrow) printf '%s' '88x56' ;;
    esac
}

latest_source=0
for source in qml/components/BarStatusPresentation.qml qml/models/BarStatusModel.js tests/qml/BarStatusCapture.qml; do
    timestamp="$(stat -c '%Y' "${repository_root}/${source}")"
    (( timestamp > latest_source )) && latest_source="${timestamp}"
done

mkdir -p "${evidence_root}"
printf 'state\ttheme\tlayout\tpath\tgeometry\n' >"${manifest}"
expected=0
for state in "${states[@]}"; do
    for theme in "${themes[@]}"; do
        for layout in "${layouts[@]}"; do
            (( expected += 1 ))
            image="${output_directory}/${state}-${theme}-${layout}.png"
            [[ -f "${image}" ]] || { printf 'missing capture: %s\n' "${image}" >&2; exit 1; }
            [[ "$(file -b --mime-type "${image}")" == 'image/png' ]] || { printf 'invalid PNG signature: %s\n' "${image}" >&2; exit 1; }
            [[ "$(identify -format '%wx%h %[channels]' "${image}")" == "$(geometry_for "${layout}") srgba"* ]] || { printf 'invalid geometry or alpha: %s\n' "${image}" >&2; exit 1; }
            [[ "$(stat -c '%s' "${image}")" -gt 128 ]] || { printf 'empty capture: %s\n' "${image}" >&2; exit 1; }
            [[ "$(stat -c '%Y' "${image}")" -ge "${latest_source}" ]] || { printf 'stale capture: %s\n' "${image}" >&2; exit 1; }
            [[ "$(identify -format '%[fx:mean]' "${image}")" != '0' ]] || { printf 'blank capture: %s\n' "${image}" >&2; exit 1; }
            printf '%s\t%s\t%s\tpng/%s-%s-%s.png\t%s\n' "${state}" "${theme}" "${layout}" "${state}" "${theme}" "${layout}" "$(geometry_for "${layout}")" >>"${manifest}"
        done
    done
done

actual="$(find "${output_directory}" -maxdepth 1 -type f -name '*.png' | wc -l)"
[[ "${actual}" -eq "${expected}" ]] || { printf 'expected %s captures, found %s\n' "${expected}" "${actual}" >&2; exit 1; }
printf 'PASS: %s verified captures; manifest: %s\n' "${expected}" "${manifest}"
