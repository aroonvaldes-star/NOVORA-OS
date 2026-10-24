#!/usr/bin/env bash
# Incluye un modelo GGUF en la ISO de NOVORA OS (se ejecuta en la máquina de
# construcción, ANTES de build-iso.sh). Exige el SHA256 publicado por el autor
# del modelo: sin hash verificado no se copia nada.
# Uso: bash scripts/add-atlas-model.sh ARCHIVO.gguf SHA256
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${ROOT}/config/includes.chroot/usr/share/novora-atlas/models"
src="${1:-}"; want="${2:-}"
if [[ -z "${src}" || -z "${want}" ]]; then
  echo "Uso: $0 ARCHIVO.gguf SHA256" >&2; exit 1
fi
[[ -f "${src}" && "${src}" == *.gguf ]] || { echo "No es un archivo .gguf: ${src}" >&2; exit 1; }
magic="$(head -c 4 "${src}")"
[[ "${magic}" == "GGUF" ]] || { echo "El archivo no tiene formato GGUF." >&2; exit 1; }
got="$(sha256sum -- "${src}" | cut -d' ' -f1)"
if [[ "${got,,}" != "${want,,}" ]]; then
  echo "SHA256 NO coincide. Esperado ${want}, obtenido ${got}. No se copia." >&2; exit 1
fi
mkdir -p "${DEST}"
cp -- "${src}" "${DEST}/"
printf '%s  %s\n' "${got}" "$(basename "${src}")" >> "${DEST}/SHA256SUMS"
echo "Modelo añadido: ${DEST}/$(basename "${src}") (recuerda revisar su licencia)."
