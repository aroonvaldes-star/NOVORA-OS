#!/usr/bin/env bash
set -Eeuo pipefail

# Genera la imagen Live ISO desde el proyecto.
# NO escribe discos. NO instala Linux en el equipo anfitrion.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$ROOT/build"
if [[ "${EUID}" -ne 0 ]]; then
  echo 'Ejecutar con sudo en un sistema de construcción Debian 13.' >&2
  exit 1
fi
if ! command -v lb >/dev/null 2>&1; then
  echo 'Falta live-build. Instalar: sudo apt install live-build debootstrap xorriso squashfs-tools' >&2
  exit 1
fi
if [[ -e "$WORK/config" ]]; then
  echo "La carpeta $WORK/config ya existe. No la sobrescribo. Usa un proyecto nuevo para una reconstrucción limpia." >&2
  exit 1
fi
mkdir -p "$WORK"
cd "$WORK"
lb config \
  --distribution trixie \
  --architectures amd64 \
  --binary-images iso-hybrid \
  --debian-installer live \
  --archive-areas 'main contrib non-free-firmware' \
  --hostname novora-os

cp -a "$ROOT/config/package-lists/." "$WORK/config/package-lists/"
mkdir -p "$WORK/config/includes.chroot"
cp -a "$ROOT/config/includes.chroot/." "$WORK/config/includes.chroot/"
chmod +x "$WORK/config/includes.chroot/usr/local/bin/novora-storage-audit"

lb build
iso="$(find "$WORK" -maxdepth 1 -type f -name '*.iso' -print -quit)"
if [[ -z "$iso" ]]; then
  echo 'La ejecución finalizó pero no encontré una ISO; revisa los logs.' >&2
  exit 2
fi
printf '\nISO generada: %s\n' "$iso"
sha256sum "$iso" > "$iso.sha256"
printf 'SHA256: %s\n' "$iso.sha256"
