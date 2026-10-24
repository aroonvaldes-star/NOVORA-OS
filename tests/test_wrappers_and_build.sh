#!/usr/bin/env bash
# shellcheck disable=SC2015  # ok() y bad() nunca fallan
# Pruebas sin root ni red: envoltorios de Calamares y build-iso.sh con
# herramientas simuladas (lb/debootstrap/xorriso/mksquashfs falsos).
set -Euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "${HERE}")"
LIB="${ROOT}/config/includes.chroot/usr/lib/novora"
TMP="$(mktemp -d)"; trap 'rm -rf "${TMP}"' EXIT
pass=0 fail=0
ok()  { echo "  PASÓ  $*"; pass=$((pass + 1)); }
bad() { echo "  FALLÓ $*"; fail=$((fail + 1)); }
mkdir -p "${TMP}/bin" "${TMP}/sys/sdb2" "${TMP}/sys/sdb3" "${TMP}/sys/nvme0n1p1"
echo 0 > "${TMP}/sys/sdb2/ro"; echo 0 > "${TMP}/sys/sdb3/ro"; echo 1 > "${TMP}/sys/nvme0n1p1/ro"

# findmnt/lsblk falsos: la ESP montada viene de $FAKE_ESP.
cat > "${TMP}/bin/findmnt" <<'EOF'
#!/bin/sh
case "$*" in *"--mountpoint /boot/efi"*) echo "$FAKE_ESP" ;; *"--mountpoint /"*) echo /dev/sdb3 ;; *) exit 1 ;; esac
EOF
cat > "${TMP}/bin/lsblk" <<'EOF'
#!/bin/sh
dev=$(for a; do :; done; echo "$a")
case "$*" in
  *FSTYPE*) echo vfat ;;
  *PKNAME*) case "$dev" in /dev/sdb*) echo sdb ;; /dev/nvme0n1*) echo nvme0n1 ;; esac ;;
esac
EOF
printf '#!/bin/sh\necho "REAL $*" > "%s/real.log"\n' "${TMP}" > "${TMP}/bin/grub-install-real"
printf '#!/bin/sh\necho "REAL $*" > "%s/efi.log"\n' "${TMP}" > "${TMP}/bin/efibootmgr-real"
chmod +x "${TMP}"/bin/*
export NOVORA_FINDMNT="${TMP}/bin/findmnt" NOVORA_LSBLK="${TMP}/bin/lsblk" \
  NOVORA_SYSBLOCK="${TMP}/sys" NOVORA_REAL_GRUB_INSTALL="${TMP}/bin/grub-install-real" \
  NOVORA_REAL_EFIBOOTMGR="${TMP}/bin/efibootmgr-real" NOVORA_EFI_LOG="${TMP}/efi-blocked.log"
G="${LIB}/grub-install-guarded"; E="${LIB}/efibootmgr-readonly"

echo "1) grub-install-guarded"
rm -f "${TMP}/real.log"
FAKE_ESP=/dev/sdb2 sh "${G}" --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=debian --force 2>/dev/null
if grep -q -- '--no-nvram' "${TMP}/real.log" 2>/dev/null && grep -q -- '--force-extra-removable' "${TMP}/real.log"; then
  ok "ESP correcta: ejecuta grub-install real con --no-nvram --force-extra-removable"; else bad "caso válido"; fi
rm -f "${TMP}/real.log"
if FAKE_ESP=/dev/nvme0n1p1 sh "${G}" --target=x86_64-efi --efi-directory=/boot/efi 2>/dev/null || [[ -f "${TMP}/real.log" ]]; then
  bad "ESP de Windows aceptada"; else ok "ESP en otro disco (Windows) rechazada sin ejecutar"; fi
if FAKE_ESP=/dev/sdb2 sh "${G}" --target=i386-pc /dev/sdb 2>/dev/null || [[ -f "${TMP}/real.log" ]]; then
  bad "GRUB BIOS aceptado"; else ok "GRUB BIOS / dispositivo de bloque rechazado"; fi
echo 1 > "${TMP}/sys/sdb2/ro"
if FAKE_ESP=/dev/sdb2 sh "${G}" --target=x86_64-efi --efi-directory=/boot/efi 2>/dev/null || [[ -f "${TMP}/real.log" ]]; then
  bad "ESP en solo-lectura aceptada"; else ok "ESP no desbloqueada por el guardián rechazada"; fi
echo 0 > "${TMP}/sys/sdb2/ro"

echo "2) efibootmgr-readonly"
rm -f "${TMP}/efi.log"; sh "${E}" -v >/dev/null
[[ -f "${TMP}/efi.log" ]] && ok "listado (-v) pasa al real" || bad "listado"
rm -f "${TMP}/efi.log"
for args in "-c -w -L debian -d /dev/sdb -p 2 -l \\EFI\\debian\\shimx64.efi" "-n 0003" "-o 0001,0000" "-B -b 0004"; do
  # shellcheck disable=SC2086
  sh "${E}" ${args} 2>/dev/null; rc=$?
  if [[ ! -f "${TMP}/efi.log" && "${rc}" -eq 0 ]]; then ok "bloqueado: efibootmgr ${args%% *} ..."; else bad "efibootmgr ${args}"; fi
done
grep -q 'bloqueado' "${TMP}/efi-blocked.log" && ok "bloqueos registrados en log" || bad "log"

echo "3) build-iso.sh con lb simulado"
P="${TMP}/proj"; cp -a "${ROOT}" "${P}"; rm -rf "${P}/build"
for t in debootstrap xorriso mksquashfs; do printf '#!/bin/sh\nexit 0\n' > "${TMP}/bin/${t}"; done
cat > "${TMP}/bin/lb" <<'EOF'
#!/bin/sh
echo "lb $*" >> lb-calls.log
case "$1" in
  --version) echo "1:20250505-fake" ;;
  config) mkdir -p config/package-lists config/includes.chroot config/hooks/normal ;;
  build) [ -x config/hooks/normal/9000-novora-hardening.hook.chroot ] || exit 9
         [ -x config/includes.chroot/usr/local/sbin/novora-disk-guard ] || exit 8
         echo ISO > live-image-amd64.hybrid.iso; echo "pkg 1" > live-image-amd64.packages ;;
  clean) rm -f live-image-amd64.hybrid.iso ;;
esac
EOF
chmod +x "${TMP}"/bin/*
run_build() { (cd "${P}" && PATH="${TMP}/bin:${PATH}" NOVORA_ALLOW_HOST=1 NOVORA_MIN_FREE_GIB=0 bash scripts/build-iso.sh "$@") >"${TMP}/b.out" 2>&1; }
if [[ "${EUID}" -ne 0 ]]; then echo "  OMITIDA (requiere root por la comprobación EUID)"; else
  run_build && ok "construcción simulada termina" || { bad "construcción simulada"; cat "${TMP}/b.out"; }
  (cd "${P}/build" && sha256sum -c novora-os-0.1.1-amd64.iso.sha256 >/dev/null) && ok "sha256sum -c verifica con ruta relativa" || bad "sha256"
  grep -q -- '--debian-installer none' "${P}/build/lb-calls.log" && ok "d-i desactivado en lb config" || bad "d-i"
  grep -q -- 'keyboard-layouts=latam' "${P}/build/lb-calls.log" && ok "teclado latam (México) en el arranque Live" || bad "teclado en bootappend"
  grep -q '^XKBLAYOUT="latam"' "${P}/config/includes.chroot/etc/default/keyboard" && \
    grep -q '^LayoutList=latam' "${P}/config/includes.chroot/etc/skel/.config/kxkbrc" && \
    grep -q '"XkbLayout" "latam"' "${P}/config/includes.chroot/etc/X11/xorg.conf.d/00-keyboard.conf" && \
    ok "teclado latam en sistema, X11/SDDM y Plasma" || bad "archivos de teclado"
  grep -q -- '--hostname' "${P}/build/lb-calls.log" && bad "usa --hostname" || ok "sin --hostname (se usa bootappend-live)"
  [[ -s "${P}/build/build.log" ]] && ok "build.log generado" || bad "build.log"
  [[ -f "${P}/build/novora-os-0.1.1-amd64.packages" ]] && ok "manifiesto de paquetes copiado" || bad "manifiesto"
  run_build && bad "segunda ejecución sin --clean" || ok "segunda ejecución sin --clean rechazada"
  run_build --clean && ok "reconstrucción con --clean" || { bad "--clean"; cat "${TMP}/b.out"; }
  run_build --work /tmp/fuera && bad "--work fuera del proyecto aceptado" || ok "--work fuera del proyecto rechazado"
  run_build --work "${P}/../escape" && bad "--work con .. aceptado" || ok "--work con .. rechazado"
fi

echo "Resultado: ${pass} PASÓ, ${fail} FALLÓ"
[[ "${fail}" -eq 0 ]]
