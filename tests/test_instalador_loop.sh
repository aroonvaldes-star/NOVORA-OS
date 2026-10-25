#!/usr/bin/env bash
# shellcheck disable=SC2015  # ok() y bad() nunca fallan
# Prueba de integración del instalador sobre un disco virtual loop que imita
# el Seagate del usuario: NTFS de datos + FAT32 de Windows (0x0c) + ext4.
# Flujo real: auditoría --esp-fat → lockdown → unlock → novora-copiar-sistema
# → lockdown. LUKS2 real (luksFormat); como el contenedor no tiene
# device-mapper, «open» se simula con un loop sobre el área de datos LUKS.
# El chroot también se simula (apt, useradd, initramfs y GRUB se registran).
# Requiere root y losetup. NO toca discos físicos.
set -Eeuo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "${HERE}")"
INC="${ROOT}/config/includes.chroot"
export NOVORA_LIB="${INC}/usr/lib/novora"
GUARD=("python3" "-I" "${INC}/usr/local/sbin/novora-disk-guard")
AUDIT=("python3" "-I" "${INC}/usr/local/bin/novora-storage-audit")
COPY="${INC}/usr/lib/novora/novora-copiar-sistema"
TMP="$(mktemp -d)"
export NOVORA_STATE_DIR="${TMP}/run"
export NOVORA_TEST_NO_SYSFS=1
SEA=''
pass=0 fail=0
ok()  { echo "  PASÓ  $*"; pass=$((pass + 1)); }
bad() { echo "  FALLÓ $*"; fail=$((fail + 1)); }
cleanup() {
  set +e
  for m in "${TMP}/mnt/boot" "${TMP}/mnt" "${TMP}/mnt.comprobar"; do mountpoint -q "${m}" && umount "${m}"; done
  [[ -L "${TMP}/mapper/novora-root" ]] && losetup -d "$(readlink "${TMP}/mapper/novora-root")"
  if [[ -n "${SEA}" ]]; then
    for n in "${SEA}" "${SEA}"p*; do [[ -b "${n}" ]] && blockdev --setrw "${n}"; done
    losetup -d "${SEA}"
  fi
  rm -rf "${TMP}"
}
trap cleanup EXIT
[[ "${EUID}" -eq 0 ]] || { echo "OMITIDA: requiere root"; exit 77; }
for t in losetup partx cryptsetup mkfs.vfat mkfs.ext4 rsync blkid; do
  command -v "${t}" >/dev/null || { echo "OMITIDA: falta ${t}"; exit 77; }
done

# Sin vfat en el kernel (contenedores de CI): montar la FAT32 con fusefat.
mkdir -p "${TMP}/bin" "${TMP}/mapper"
if ! grep -qw vfat /proc/filesystems; then
  command -v fusefat >/dev/null || { echo "OMITIDA: el kernel no tiene vfat y falta fusefat"; exit 77; }
  cat > "${TMP}/bin/mount" <<'EOF'
#!/bin/sh
for a; do last2="$last"; last="$a"; done
if [ "$(blkid -o value -s TYPE "$last2" 2>/dev/null)" = vfat ]; then
  case " $* " in *" ro "*|*" ro,"*) exec fusefat -o ro "$last2" "$last" ;; esac
  exec fusefat -o rw+ "$last2" "$last"
fi
exec /usr/bin/mount "$@"
EOF
  chmod +x "${TMP}/bin/mount"
  export PATH="${TMP}/bin:${PATH}"
fi

# Seagate virtual (MBR, firma 5ea00042): datos 0x07, FAT32 0x0c, destino 0x83.
truncate -s 3100M "${TMP}/sea.img"
python3 -I - "${TMP}/sea.img" <<'EOF'
import struct, sys
mbr = bytearray(512)
mbr[440:444] = struct.pack('<I', 0x5ea00042)
for i, (t, s, n) in enumerate([(0x07, 2048, 204800), (0x0c, 206848, 4718592), (0x83, 4925440, 1228800)]):
    mbr[446 + 16 * i:462 + 16 * i] = struct.pack('<B3sB3sII', 0, b'\0' * 3, t, b'\0' * 3, s, n)
mbr[510:512] = b'\x55\xaa'
with open(sys.argv[1], 'r+b') as fh:
    fh.write(mbr)
EOF
SEA="$(losetup -f --show "${TMP}/sea.img")"
partx -a "${SEA}" 2>/dev/null || true
for _ in $(seq 1 20); do [[ -b "${SEA}p3" ]] && break; sleep 0.5; done
head -c 1M /dev/urandom > "${TMP}/datos.bin"
dd if="${TMP}/datos.bin" of="${SEA}p1" bs=1M conv=fsync status=none     # «NTFS» del usuario
mkfs.vfat -F 32 -n NOVORA-EFI "${SEA}p2" >/dev/null
mkdir -p "${TMP}/m"; mount "${SEA}p2" "${TMP}/m"; echo "mis fotos" > "${TMP}/m/FOTO.TXT"; umount "${TMP}/m"
mkfs.ext4 -q -F "${SEA}p3"
mount "${SEA}p3" "${TMP}/m"; echo "importante" > "${TMP}/m/tesis.docx"; umount "${TMP}/m"
p1_hash="$(sha256sum < "${SEA}p1")"
echo "Disco virtual: ${SEA}"

python3 -I - "${SEA}" > "${TMP}/tree.json" <<'EOF'
import json, sys
sea = sys.argv[1]
G = 1024 ** 3
def p(n, size, start, fs, pt):
    return {"name": f"{sea.split('/')[-1]}p{n}", "path": f"{sea}p{n}", "type": "part",
            "size": size, "start": start, "fstype": fs, "parttype": pt,
            "partuuid": f"5ea00042-0{n}", "mountpoints": [None], "children": []}
print(json.dumps({"blockdevices": [{
    "name": sea.split('/')[-1], "path": sea, "type": "disk", "size": 3100 * 1024 ** 2,
    "model": "VIRTUAL", "serial": "SEAVIRT42", "wwn": None, "tran": "usb", "pttype": "dos",
    "ptuuid": "5ea00042", "log-sec": 512, "children": [
        p(1, 204800 * 512, 2048, "ntfs", "0x7"),
        p(2, 4718592 * 512, 206848, "vfat", "0xc"),
        p(3, 50 * G, 4925440, "ext4", "0x83")]}]}))   # 50 GiB declarados: supera B09
EOF
export NOVORA_LSBLK_JSON="${TMP}/tree.json"

# cryptsetup: luksFormat real; open/close simulados con un loop sobre los datos.
REAL_CRYPT="$(command -v cryptsetup)"
cat > "${TMP}/bin/cryptsetup" <<EOF
#!/bin/sh
case "\$1" in
  luksFormat) exec "${REAL_CRYPT}" "\$@" --pbkdf-memory 65536 ;;
  open) for a; do dev="\$name"; name="\$a"; done
        off=\$("${REAL_CRYPT}" luksDump "\$dev" | awk '/offset:/ { print \$2; exit }')
        ln -sf "\$(losetup -f --show -o "\$off" "\$dev")" "${TMP}/mapper/\$name" ;;
  close) losetup -d "\$(readlink "${TMP}/mapper/\$2")" && rm -f "${TMP}/mapper/\$2" ;;
  *) exit 1 ;;
esac
EOF
# chroot simulado: registra cada orden y crea lo que dejarían GRUB y update-grub.
cat > "${TMP}/bin/chroot" <<'EOF'
#!/bin/sh
mnt="$1"; shift
echo "$*" >> "${mnt}/../chroot.log"
case "$1" in
  getent) [ "$3" = sudo ] || [ "$3" = plugdev ] ;;
  env) mkdir -p "${mnt}/boot/EFI/BOOT" "${mnt}/boot/EFI/debian"
       echo shim > "${mnt}/boot/EFI/BOOT/BOOTX64.EFI" ;;
  update-grub) mkdir -p "${mnt}/boot/grub" "${mnt}/boot/EFI/debian"
               echo menu > "${mnt}/boot/grub/grub.cfg"
               echo "configfile (\$root)/grub/grub.cfg" > "${mnt}/boot/EFI/debian/grub.cfg" ;;
esac
EOF
chmod +x "${TMP}/bin/"*
mkdir -p "${TMP}/src/usr/bin" "${TMP}/src/etc" "${TMP}/src/boot" "${TMP}/src/home"
echo novora > "${TMP}/src/etc/hostname"
echo kernel > "${TMP}/src/boot/vmlinuz-6.12.0-novora"
echo initrd > "${TMP}/src/boot/initrd.img-6.12.0-novora"
ln -s vmlinuz-6.12.0-novora "${TMP}/src/boot/vmlinuz"                # FAT32: se omite
printf 'clave-de-prueba' > "${TMP}/key"
export NOVORA_SOURCE_ROOT="${TMP}/src" NOVORA_TARGET_MNT="${TMP}/mnt" \
  NOVORA_CRYPTSETUP="${TMP}/bin/cryptsetup" NOVORA_MAPPER_DIR="${TMP}/mapper" \
  NOVORA_LUKS_KEYFILE="${TMP}/key" NOVORA_CHROOT="${TMP}/bin/chroot" NOVORA_SKIP_BIND=1 \
  NOVORA_USER=aroon NOVORA_TEST_NO_PASSWD=1

echo "1) auditoría: la FAT32 de Windows solo se acepta con --esp-fat"
if "${AUDIT[@]}" --assume-uefi --target "${SEA}p3" --esp "${SEA}p2" >/dev/null; then
  bad "FAT32 0x0c aceptada sin --esp-fat"; else ok "FAT32 0x0c rechazada sin --esp-fat"; fi
"${AUDIT[@]}" --assume-uefi --esp-fat --target "${SEA}p3" --esp "${SEA}p2" \
  --emit-allowlist "${TMP}/allow.json" >/dev/null && ok "aprobada con --esp-fat (avisos W05/W10)" || bad "auditoría"
"${GUARD[@]}" lockdown >/dev/null
"${GUARD[@]}" unlock --allowlist "${TMP}/allow.json" --apply >/dev/null && ok "unlock del destino" || bad "unlock"

echo "2) el destino con archivos exige escribir BORRAR"
if echo "no" | "${COPY}" --allowlist "${TMP}/allow.json" >/dev/null 2>&1; then
  bad "continuó sin BORRAR"; else ok "sin BORRAR se cancela"; fi
[[ "$(blkid -o value -s TYPE "${SEA}p3")" == "ext4" ]] && ok "ext4 intacta tras cancelar" || bad "destino modificado al cancelar"

echo "3) instalación completa"
if echo "BORRAR" | "${COPY}" --allowlist "${TMP}/allow.json" > "${TMP}/copy.log" 2>&1; then
  ok "novora-copiar-sistema terminó"; else bad "novora-copiar-sistema falló:"; tail -n 15 "${TMP}/copy.log"; fi
[[ "$(blkid -o value -s TYPE "${SEA}p3")" == "crypto_LUKS" ]] && ok "destino cifrado con LUKS2" || bad "destino sin LUKS"
"${REAL_CRYPT}" luksDump "${SEA}p3" | grep -q "argon2id" && ok "LUKS2 con argon2id" || bad "pbkdf"
"${REAL_CRYPT}" luksDump "${SEA}p3" | grep -qE "sector: *4096" && ok "sectores de 4096" || bad "tamaño de sector"
[[ "$(sha256sum < "${SEA}p1")" == "${p1_hash}" ]] && ok "partición de datos (NTFS) intacta" || bad "NTFS MODIFICADA"
"${TMP}/bin/cryptsetup" open --key-file "${TMP}/key" "${SEA}p3" novora-root
mkdir -p "${TMP}/mnt"; mount "${TMP}/mapper/novora-root" "${TMP}/mnt"; mount "${SEA}p2" "${TMP}/mnt/boot"
[[ -f "${TMP}/mnt/etc/hostname" ]] && ok "sistema copiado" || bad "falta el sistema"
[[ -f "${TMP}/mnt/boot/FOTO.TXT" ]] && ok "archivos previos de la FAT32 conservados" || bad "FAT32 borrada"
[[ -f "${TMP}/mnt/boot/vmlinuz-6.12.0-novora" && ! -e "${TMP}/mnt/boot/vmlinuz" ]] && ok "núcleo en /boot (FAT32, sin enlaces)" || bad "núcleo"
luks="$(blkid -o value -s UUID "${SEA}p3")"
grep -q "UUID=${luks}  none  luks,initramfs" "${TMP}/mnt/etc/crypttab" && ok "crypttab por UUID" || bad "crypttab"
grep -qE "^UUID=.* /boot +vfat" "${TMP}/mnt/etc/fstab" && grep -qE "^UUID=.* / +ext4" "${TMP}/mnt/etc/fstab" && ok "fstab" || bad "fstab"
grep -q "KEYMAP=y" "${TMP}/mnt/etc/initramfs-tools/conf.d/novora-teclado.conf" && ok "teclado en el initramfs" || bad "KEYMAP"
grep -q '"backup_device_uuid"' "${TMP}/mnt/etc/timeshift/timeshift.json" && ok "Timeshift configurado" || bad "timeshift"
grep -q "useradd -m -s /bin/bash -G sudo,plugdev aroon" "${TMP}/chroot.log" && ok "cuenta creada" || bad "useradd"
grep -q -- "--efi-directory=/boot --boot-directory=/boot --bootloader-id=debian" "${TMP}/chroot.log" \
  && grep -q "grub-install-guarded" "${TMP}/chroot.log" && ok "GRUB por el envoltorio sin NVRAM" || bad "grub-install"
[[ -f "${TMP}/mnt/boot/EFI/BOOT/grub.cfg" ]] && ok "grub.cfg en la ruta extraíble" || bad "EFI/BOOT/grub.cfg"
umount "${TMP}/mnt/boot" "${TMP}/mnt"; "${TMP}/bin/cryptsetup" close novora-root

echo "4) lockdown final"
"${GUARD[@]}" lockdown >/dev/null
for n in "${SEA}p2" "${SEA}p3"; do
  [[ "$(cat "/sys/class/block/$(basename "${n}")/ro")" == 1 ]] && ok "${n} en solo lectura" || bad "${n} escribible"
done

echo "Resultado: ${pass} PASÓ, ${fail} FALLÓ"
[[ "${fail}" -eq 0 ]]
