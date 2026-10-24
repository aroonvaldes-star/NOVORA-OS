#!/usr/bin/env bash
# shellcheck disable=SC2015  # ok() y bad() nunca fallan
# Prueba de integración del guardián con el KERNEL real, sobre dos discos
# virtuales loop desechables ("Windows" y "Seagate"). Requiere root y losetup.
# NO toca discos físicos: solo archivos de imagen en un directorio temporal.
set -Eeuo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "${HERE}")"
INC="${ROOT}/config/includes.chroot"
export NOVORA_LIB="${INC}/usr/lib/novora"
GUARD=("python3" "-I" "${INC}/usr/local/sbin/novora-disk-guard")
AUDIT=("python3" "-I" "${INC}/usr/local/bin/novora-storage-audit")
UDEV="${INC}/usr/lib/novora/novora-udev-ro"
TMP="$(mktemp -d)"
export NOVORA_STATE_DIR="${TMP}/run"
export NOVORA_TEST_NO_SYSFS=1   # no bloquear el disco del anfitrión de pruebas
WIN='' SEA=''
pass=0 fail=0
ok()  { echo "  PASÓ  $*"; pass=$((pass + 1)); }
bad() { echo "  FALLÓ $*"; fail=$((fail + 1)); }
cleanup() {
  for d in "${WIN}" "${SEA}"; do
    [[ -n "${d}" ]] || continue
    for n in "${d}" "${d}"p*; do [[ -b "${n}" ]] && blockdev --setrw "${n}" 2>/dev/null; done
    losetup -d "${d}" 2>/dev/null || true
  done
  rm -rf "${TMP}"
}
trap cleanup EXIT
[[ "${EUID}" -eq 0 ]] || { echo "OMITIDA: requiere root"; exit 77; }
command -v losetup >/dev/null || { echo "OMITIDA: sin losetup"; exit 77; }

mkimg() {  # $1 archivo, $2 firma MBR, $3.. "tipo:inicio:sectores"
  local f="$1" sig="$2"; shift 2
  truncate -s 300M "${f}"
  python3 -I - "${f}" "${sig}" "$@" <<'EOF'
import struct, sys
f, sig, parts = sys.argv[1], int(sys.argv[2], 16), sys.argv[3:]
mbr = bytearray(512)
mbr[440:444] = struct.pack('<I', sig)
for i, p in enumerate(parts):
    t, s, n = (int(x, 0) for x in p.split(':'))
    mbr[446 + 16 * i:462 + 16 * i] = struct.pack('<B3sB3sII', 0, b'\0' * 3, t, b'\0' * 3, s, n)
mbr[510:512] = b'\x55\xaa'
with open(f, 'r+b') as fh:
    fh.write(mbr)
EOF
}
attach() { local d; d="$(losetup -f --show "$1")"; partx -a "${d}" 2>/dev/null || true; echo "${d}"; }

# Windows: ESP(0xef) + datos(0x07).  Seagate: datos(0x07) + ESP(0xef) + destino(0x83).
mkimg "${TMP}/win.img" aaaa0001 0xef:2048:40960 0x07:43008:200000
mkimg "${TMP}/sea.img" 5ea00042 0x07:2048:100000 0xef:102048:40960 0x83:143008:400000
WIN="$(attach "${TMP}/win.img")"; SEA="$(attach "${TMP}/sea.img")"
echo "Discos virtuales: Windows=${WIN} Seagate=${SEA}"

# Árbol lsblk equivalente con identidades ficticias (los loop no tienen serie).
python3 -I - "${WIN}" "${SEA}" > "${TMP}/tree.json" <<'EOF'
import json, sys
win, sea = sys.argv[1:]
G = 1024 ** 3
def p(path, n, size, start, fs, pt, uuid):
    return {"name": path.split('/')[-1], "path": f"{path}p{n}", "type": "part",
            "size": size, "start": start, "fstype": fs, "parttype": pt,
            "partuuid": uuid, "mountpoints": [None], "children": []}
def d(path, serial, tran, ptuuid, parts):
    return {"name": path.split('/')[-1], "path": path, "type": "disk",
            "size": 300 * 1024 ** 2, "model": "VIRTUAL", "serial": serial,
            "wwn": None, "tran": tran, "pttype": "dos", "ptuuid": ptuuid,
            "log-sec": 512, "children": parts}
tree = {"blockdevices": [
    d(win, "WINVIRT01", "nvme", "aaaa0001", [
        p(win, 1, 40960 * 512, 2048, "vfat", "0xef", "aaaa0001-01"),
        p(win, 2, 200000 * 512, 43008, "ntfs", "0x7", "aaaa0001-02")]),
    d(sea, "SEAVIRT42", "usb", "5ea00042", [
        p(sea, 1, 100000 * 512, 2048, "ntfs", "0x7", "5ea00042-01"),
        p(sea, 2, 40960 * 512, 102048, "vfat", "0xef", "5ea00042-02"),
        # tamaño declarado >= 40 GiB para superar B09 en la simulación
        p(sea, 3, 50 * G, 143008, None, "0x83", "5ea00042-03")])]}
print(json.dumps(tree))
EOF
export NOVORA_LSBLK_JSON="${TMP}/tree.json"

canwrite() {  # 0 si se puede escribir un bloque en el nodo
  python3 -I -c '
import os, sys
try:
    fd = os.open(sys.argv[1], os.O_WRONLY); os.pwrite(fd, b"N" * 512, 65536); os.fsync(fd); os.close(fd)
except OSError:
    sys.exit(1)' "$1"
}
expect_ro() { if canwrite "$1"; then bad "$2: $1 ESCRIBIBLE"; else ok "$2: $1 bloqueado"; fi; }
expect_rw() { if canwrite "$1"; then ok "$2: $1 escribible"; else bad "$2: $1 BLOQUEADO"; fi; }

echo "1) Auditoría y autorización"
"${AUDIT[@]}" --assume-uefi --target "${SEA}p3" --esp "${SEA}p2" \
  --emit-allowlist "${TMP}/allow.json" >/dev/null && ok "auditoría aprueba Seagate p3 + ESP p2" || bad "auditoría"
if "${AUDIT[@]}" --assume-uefi --target "${SEA}p3" --esp "${WIN}p1" >/dev/null; then
  bad "ESP de Windows aceptada"; else ok "ESP de Windows rechazada"; fi

echo "2) lockdown (estado de arranque Live)"
"${GUARD[@]}" lockdown >/dev/null
for n in "${WIN}" "${WIN}p1" "${WIN}p2" "${SEA}" "${SEA}p1" "${SEA}p2" "${SEA}p3"; do expect_ro "${n}" lockdown; done

echo "3) unlock --apply (solo destino autorizado)"
"${GUARD[@]}" unlock --allowlist "${TMP}/allow.json" --apply >/dev/null && ok "unlock + verify" || bad "unlock"
for n in "${WIN}" "${WIN}p1" "${WIN}p2" "${SEA}p1"; do expect_ro "${n}" unlock; done
for n in "${SEA}p2" "${SEA}p3"; do expect_rw "${n}" unlock; done
if mkfs.ext4 -q -F "${WIN}p2" 2>/dev/null; then bad "mkfs en disco Windows"; else ok "mkfs en disco Windows rechazado"; fi

echo "4) relectura de tabla en el Seagate (como haría un particionador)"
# Relectura completa y fiable: udev (en servidores de CI) puede tener abierta una
# partición un instante y entonces partx -d no la quita; se espera y se reintenta.
reread() {
  local _
  for _ in $(seq 1 20); do
    command -v udevadm >/dev/null && udevadm settle 2>/dev/null || true
    partx -d "${SEA}" 2>/dev/null || true
    compgen -G "${SEA}p*" >/dev/null || break
    sleep 0.5
  done
  compgen -G "${SEA}p*" >/dev/null && { bad "no se pudieron quitar las particiones de ${SEA}"; return 1; }
  for _ in $(seq 1 20); do
    partx -a "${SEA}" 2>/dev/null && [[ -b "${SEA}p3" ]] && return 0
    command -v udevadm >/dev/null && udevadm settle 2>/dev/null || true
    sleep 0.5
  done
  bad "partx -a ${SEA}"; return 1
}
reread
expect_rw "${SEA}p1" "sin udev (limitación conocida)"
for n in 1 2 3; do  # lo que haría la regla udev al recibir 'add'
  env -i DEVNAME="${SEA}p${n}" DEVTYPE=partition ID_SERIAL_SHORT=SEAVIRT42 \
    ID_PART_ENTRY_UUID="5ea00042-0${n}" NOVORA_STATE_DIR="${NOVORA_STATE_DIR}" \
    NOVORA_CMDLINE=<(echo "boot=live components") sh "${UDEV}"
done
expect_ro "${SEA}p1" "tras regla udev"
expect_rw "${SEA}p3" "tras regla udev"
"${GUARD[@]}" verify --allowlist "${TMP}/allow.json" >/dev/null && ok "verify tras relectura" || bad "verify"

echo "5) disco desconocido conectado durante la instalación"
env -i DEVNAME="${WIN}p2" DEVTYPE=partition ID_SERIAL_SHORT=OTRO \
  ID_PART_ENTRY_UUID=aaaa0001-02 NOVORA_STATE_DIR="${NOVORA_STATE_DIR}" \
  NOVORA_CMDLINE=<(echo "boot=live") sh "${UDEV}"
expect_ro "${WIN}p2" "udev disco no autorizado"

echo "6) desconexión del Seagate (T06): verify debe fallar"
python3 -I -c 'import json,sys; t=json.load(open(sys.argv[1])); t["blockdevices"]=t["blockdevices"][:1]; json.dump(t,open(sys.argv[2],"w"))' \
  "${TMP}/tree.json" "${TMP}/unplugged.json"
if NOVORA_LSBLK_JSON="${TMP}/unplugged.json" "${GUARD[@]}" verify --allowlist "${TMP}/allow.json" 2>/dev/null; then
  bad "verify sin Seagate"; else ok "verify sin Seagate falla (fail-closed)"; fi

echo "7) lockdown final"
"${GUARD[@]}" lockdown >/dev/null
for n in "${SEA}p2" "${SEA}p3"; do expect_ro "${n}" "lockdown final"; done

echo "Resultado: ${pass} PASÓ, ${fail} FALLÓ"
[[ "${fail}" -eq 0 ]]
