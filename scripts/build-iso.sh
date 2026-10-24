#!/usr/bin/env bash
# shellcheck disable=SC1091  # /etc/os-release es del anfitrión
# NOVORA OS 0.1.1 — genera la imagen Live ISO desde el proyecto.
# NO escribe discos. NO instala Linux en el equipo anfitrión. Solo crea
# archivos dentro de la carpeta de trabajo (por defecto ./build).
#
# Uso: sudo bash scripts/build-iso.sh [--work DIR] [--clean] [--atlas-required]
#   --clean           borra una construcción previa en DIR (solo dentro del proyecto)
#   --atlas-required  falla si no se puede instalar el motor de ATLAS
set -Eeuo pipefail

VERSION="0.1.1"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${ROOT}/build"
CLEAN=0
ATLAS_ENGINE=optional

on_err() { echo "ERROR en línea $1 (código $2). Revisa ${WORK}/build.log" >&2; }
trap 'on_err "${LINENO}" "$?"' ERR

while [[ $# -gt 0 ]]; do
  case "$1" in
    --work) WORK="$(realpath -m -- "$2")"; shift 2 ;;
    --clean) CLEAN=1; shift ;;
    --atlas-required) ATLAS_ENGINE=required; shift ;;
    -h|--help) sed -n '3,9p' "$0"; exit 0 ;;
    *) echo "Opción desconocida: $1" >&2; exit 1 ;;
  esac
done

case "${WORK}/" in
  "${ROOT}/"?*) ;;
  *) echo "La carpeta de trabajo debe estar DENTRO del proyecto (${ROOT})." >&2; exit 1 ;;
esac
if [[ "${EUID}" -ne 0 ]]; then
  echo 'Ejecutar con sudo en un sistema de construcción Debian 13.' >&2
  exit 1
fi
for tool in lb debootstrap xorriso mksquashfs sha256sum; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "Falta ${tool}. Instalar: sudo apt install live-build debootstrap xorriso squashfs-tools" >&2
    exit 1
  fi
done
codename="$(. /etc/os-release && echo "${VERSION_CODENAME:-}")"
if [[ "${codename}" != "trixie" && "${NOVORA_ALLOW_HOST:-0}" != "1" ]]; then
  echo "El anfitrión es '${codename:-desconocido}', no Debian 13 trixie. Usa una VM Debian 13" >&2
  echo "o exporta NOVORA_ALLOW_HOST=1 bajo tu responsabilidad." >&2
  exit 1
fi

if [[ -e "${WORK}/config" ]]; then
  if [[ "${CLEAN}" -ne 1 ]]; then
    echo "Ya existe ${WORK}/config. Usa --clean para reconstruir desde cero." >&2
    exit 1
  fi
  (cd "${WORK}" && lb clean --purge)
  rm -rf -- "${WORK:?}/config" "${WORK:?}/auto" "${WORK:?}/local"
fi
mkdir -p "${WORK}"
avail_kb="$(df --output=avail -k "${WORK}" | tail -1 | tr -d ' ')"
min_gib="${NOVORA_MIN_FREE_GIB:-25}"
if [[ "${avail_kb}" -lt $((min_gib * 1024 * 1024)) ]]; then
  echo "Se necesitan al menos ${min_gib} GiB libres en ${WORK}." >&2
  exit 1
fi

cd "${WORK}"
LOG="${WORK}/build.log"
: > "${LOG}"
{
  echo "NOVORA OS ${VERSION} — construcción $(date -u +%FT%TZ)"
  echo "anfitrión: $(. /etc/os-release && echo "${PRETTY_NAME}") $(uname -r)"
  echo "live-build: $(lb --version 2>/dev/null || dpkg-query -W -f='${Version}' live-build 2>/dev/null || echo '?')"
  if git -C "${ROOT}" rev-parse HEAD >/dev/null 2>&1; then
    echo "git: $(git -C "${ROOT}" rev-parse HEAD) $(git -C "${ROOT}" status --porcelain | wc -l) cambios sin commit"
  fi
} | tee -a "${LOG}"

# --debian-installer none: el instalador clásico de Debian (d-i) aparecería en
# el menú de arranque como un SEGUNDO instalador, sin el guardián de discos.
# hostname/usuario se pasan a live-config por la línea de arranque.
lb config \
  --distribution trixie \
  --architectures amd64 \
  --binary-images iso-hybrid \
  --bootloaders "grub-efi,syslinux" \
  --debian-installer none \
  --archive-areas "main contrib non-free-firmware" \
  --bootappend-live "boot=live components hostname=novora-os username=novora keyboard-model=pc105 keyboard-layouts=latam" \
  --iso-volume "NOVORA-OS ${VERSION}" \
  --iso-application "NOVORA OS ${VERSION}" \
  2>&1 | tee -a "${LOG}"

cp -a "${ROOT}/config/package-lists/." "${WORK}/config/package-lists/"
mkdir -p "${WORK}/config/includes.chroot" "${WORK}/config/hooks/normal"
cp -a "${ROOT}/config/includes.chroot/." "${WORK}/config/includes.chroot/"
cp -a "${ROOT}/config/hooks/normal/." "${WORK}/config/hooks/normal/"
mkdir -p "${WORK}/config/includes.chroot/etc/novora-atlas"
printf 'NOVORA_ATLAS_ENGINE=%s\n' "${ATLAS_ENGINE}" > "${WORK}/config/includes.chroot/etc/novora-atlas/build.conf"
mkdir -p "${WORK}/config/includes.chroot/usr/share/doc/novora"
cp -a "${ROOT}/docs/." "${WORK}/config/includes.chroot/usr/share/doc/novora/"
find "${WORK}/config/includes.chroot/usr/local" "${WORK}/config/includes.chroot/usr/lib/novora" \
  "${WORK}/config/hooks" -type f ! -name '*.py' -exec chmod 0755 {} +

lb build 2>&1 | tee -a "${LOG}"

iso="${WORK}/live-image-amd64.hybrid.iso"
if [[ ! -f "${iso}" ]]; then
  echo "La construcción terminó pero no existe ${iso}; revisa ${LOG}." >&2
  exit 2
fi
final="${WORK}/novora-os-${VERSION}-amd64.iso"
mv -f -- "${iso}" "${final}"
for m in live-image-amd64.packages chroot.packages.live; do
  if [[ -f "${WORK}/${m}" ]]; then cp -a "${WORK}/${m}" "${final%.iso}.packages"; break; fi
done
(cd "${WORK}" && sha256sum -- "$(basename "${final}")" > "$(basename "${final}").sha256")
printf '\nISO: %s\nSHA256: %s\nLog: %s\n' "${final}" "$(cut -d' ' -f1 "${final}.sha256")" "${LOG}"
