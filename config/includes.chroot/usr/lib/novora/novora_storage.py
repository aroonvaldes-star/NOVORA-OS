"""NOVORA OS — biblioteca común de identificación y evaluación de almacenamiento.

Solo lectura: este módulo NO escribe en discos. Las funciones que cambian el
indicador de solo-lectura del kernel viven en novora-disk-guard.

Política: FAIL-CLOSED. Cualquier dato ausente, ambiguo o desconocido produce un
hallazgo BLOCK. Una instalación solo puede continuar si no hay ningún BLOCK.
"""
import datetime
import json
import os
import subprocess

SCHEMA = 1
FIELDS = ("NAME,PATH,TYPE,SIZE,MODEL,SERIAL,WWN,TRAN,HOTPLUG,RM,RO,FSTYPE,"
          "MOUNTPOINTS,PTTYPE,PTUUID,PARTTYPE,PARTUUID,PARTLABEL,LOG-SEC,"
          "PHY-SEC,START")
ESP_TYPES = {"c12a7328-f81f-11d2-ba4b-00a0c93ec93b", "0xef"}
LIVE_MOUNT_PREFIXES = ("/run/live", "/lib/live/mount")
# Sistemas de archivos que casi siempre contienen datos de Windows/usuario o
# capas que no deben reformatearse desde este instalador.
DATA_FS_BLOCK = {"ntfs", "BitLocker", "exfat", "vfat", "crypto_LUKS",
                 "LVM2_member", "linux_raid_member", "zfs_member", "apfs",
                 "hfsplus", "hfs", "ReFS", "refs", "iso9660", "udf",
                 "swap", "bcache", "ceph", "drbd"}
# Sistemas Linux que pueden ser un destino preparado, pero también datos.
LINUX_FS_WARN = {"ext4", "ext3", "ext2", "xfs", "btrfs", "f2fs"}
MIN_ROOT_BYTES = 40 * 1024 ** 3
MBR_MAX_SECTORS = 2 ** 32
BLOCK, WARN, INFO = "BLOCK", "WARN", "INFO"


class StorageError(Exception):
    pass


def _bool(v):
    if isinstance(v, bool):
        return v
    return str(v).strip() in ("1", "true", "True")


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def load_tree(json_path=None):
    """Devuelve la lista de dispositivos de lsblk (árbol completo).

    json_path o la variable NOVORA_LSBLK_JSON permiten pruebas con fixtures.
    """
    json_path = json_path or os.environ.get("NOVORA_LSBLK_JSON")
    if json_path:
        with open(json_path, encoding="utf-8") as fh:
            data = json.load(fh)
    else:
        try:
            out = subprocess.run(["lsblk", "--json", "--bytes", "--tree",
                                  "--output", FIELDS], text=True,
                                 capture_output=True, check=True).stdout
        except (OSError, subprocess.CalledProcessError) as ex:
            raise StorageError(f"lsblk falló: {ex}") from ex
        data = json.loads(out)
    devs = data.get("blockdevices")
    if not isinstance(devs, list):
        raise StorageError("salida de lsblk sin 'blockdevices'")
    return devs


def walk(node):
    yield node
    for ch in node.get("children") or []:
        yield from walk(ch)


def mountpoints(node):
    mps = node.get("mountpoints")
    if mps is None:
        mps = [node.get("mountpoint")]
    return [m for m in mps if m]


def mounted_anywhere(node):
    """Montajes del nodo o de cualquier descendiente (LUKS, LVM...)."""
    found = []
    for n in walk(node):
        for m in mountpoints(n):
            found.append((n.get("path"), m))
    return found


def disks(tree):
    return [d for d in tree if d.get("type") == "disk"]


def partitions(disk):
    return [p for p in disk.get("children") or [] if p.get("type") == "part"]


def is_live_medium(disk):
    for n in walk(disk):
        if n.get("fstype") == "iso9660":
            return True
        for m in mountpoints(n):
            if m.startswith(LIVE_MOUNT_PREFIXES):
                return True
    return False


def is_esp(part):
    return (str(part.get("parttype") or "").lower() in ESP_TYPES
            and part.get("fstype") == "vfat")


def identity(disk):
    return {
        "serial": (disk.get("serial") or "").strip() or None,
        "wwn": (disk.get("wwn") or "").strip() or None,
        "model": (disk.get("model") or "").strip() or None,
        "size": _int(disk.get("size")),
        "pttype": disk.get("pttype"),
        "ptuuid": disk.get("ptuuid"),
        "log_sec": _int(disk.get("log-sec")),
        "tran": disk.get("tran"),
    }


def same_identity(a, b):
    """Coincidencia estricta: serial/WWN (al menos uno presente y ambos
    iguales cuando existen) + tamaño + PTUUID."""
    if not (a.get("serial") or a.get("wwn")):
        return False
    for key in ("serial", "wwn"):
        if a.get(key) and a.get(key) != b.get(key):
            return False
    return (a.get("size") == b.get("size")
            and a.get("ptuuid") and a.get("ptuuid") == b.get("ptuuid"))


def part_record(part):
    return {"partuuid": (part.get("partuuid") or "").lower() or None,
            "path_at_audit": part.get("path"),
            "size": _int(part.get("size")),
            "start": _int(part.get("start")),
            "fstype": part.get("fstype"),
            "parttype": str(part.get("parttype") or "").lower() or None}


def mask(value):
    if not value:
        return "(no informado)"
    value = str(value)
    return "…" + value[-4:] if len(value) > 4 else "…"


def human(num):
    n = _int(num)
    if n is None:
        return "?"
    f = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if f < 1024 or unit == "TiB":
            return f"{f:.1f} {unit}"
        f /= 1024
    return "?"


def find_part(tree, path):
    for d in disks(tree):
        for p in partitions(d):
            if p.get("path") == path:
                return d, p
    return None, None


def evaluate(tree, target_path, esp_path, uefi):
    """Evalúa una selección. Devuelve (hallazgos, allowlist|None).

    hallazgos: lista de (nivel, código, mensaje). allowlist solo se emite si
    no hay ningún BLOCK.
    """
    f = []

    def add(level, code, msg):
        f.append((level, code, msg))

    disk, part = find_part(tree, target_path)
    if part is None:
        add(BLOCK, "B00", f"La partición destino {target_path} no existe.")
        return f, None
    if not uefi:
        add(BLOCK, "B13", "Arranque BIOS/Legacy: Windows 11 usa UEFI; un "
            "GRUB BIOS escribiría código en el MBR. Arranca la ISO en UEFI.")
    ident = identity(disk)
    if ident["tran"] != "usb":
        add(BLOCK, "B01", f"{disk.get('path')} no está identificado como USB "
            f"(bus={ident['tran'] or 'desconocido'}).")
    if not (ident["serial"] or ident["wwn"]):
        add(BLOCK, "B02", "El disco no informa número de serie ni WWN: no se "
            "puede identificar de forma estable.")
    if not ident["ptuuid"]:
        add(BLOCK, "B12", "El disco no informa identificador de tabla "
            "(PTUUID).")
    if is_live_medium(disk):
        add(BLOCK, "B03", "Ese disco contiene el medio Live en ejecución.")
    if ident["pttype"] not in ("gpt", "dos"):
        add(BLOCK, "B06", f"Tabla de particiones desconocida: "
            f"{ident['pttype'] or 'no informada'}.")
    # Duplicados/ambigüedad entre discos conectados.
    for other in disks(tree):
        if other is disk:
            continue
        oi = identity(other)
        dup_serial = ident["serial"] and oi["serial"] == ident["serial"]
        dup_wwn = ident["wwn"] and oi["wwn"] == ident["wwn"]
        dup_noid = (not (oi["serial"] or oi["wwn"]) and oi["model"]
                    and oi["model"] == ident["model"]
                    and oi["size"] == ident["size"])
        if dup_serial or dup_wwn or dup_noid:
            add(BLOCK, "B10", f"Identidad ambigua: {other.get('path')} parece "
                "el mismo modelo/serie. Desconecta los otros discos externos.")
    # Destino.
    mnt = mounted_anywhere(part)
    if mnt:
        add(BLOCK, "B04", f"La partición destino (o algo dentro) está montada: "
            f"{mnt}.")
    rec = part_record(part)
    if not rec["partuuid"]:
        add(BLOCK, "B11", "La partición destino no tiene PARTUUID.")
    fs = part.get("fstype")
    if fs in DATA_FS_BLOCK:
        add(BLOCK, "B05", f"La partición destino contiene '{fs}': probable "
            "dato de Windows/usuario o capa cifrada/LVM. No se usará.")
    elif fs in LINUX_FS_WARN:
        add(WARN, "W05", f"La partición destino ya tiene '{fs}'. Formatearla "
            "borra su contenido: confirma que es el destino preparado.")
    elif fs:
        add(BLOCK, "B05", f"Sistema de archivos no reconocido '{fs}' "
            "(fail-closed).")
    if (rec["size"] or 0) < MIN_ROOT_BYTES:
        add(BLOCK, "B09", f"Partición destino demasiado pequeña "
            f"({human(rec['size'])}; mínimo 40 GiB).")
    # Límites MBR.
    ls = ident["log_sec"] or 512
    if ident["pttype"] == "dos":
        if (ident["size"] or 0) > MBR_MAX_SECTORS * ls:
            add(WARN, "W07", f"Disco MBR de {human(ident['size'])} con sector "
                f"lógico {ls} B: lo que pase de {human(MBR_MAX_SECTORS * ls)} "
                "no es direccionable por MBR.")
        if ls != 512:
            add(WARN, "W08", f"Sector lógico de {ls} B informado por el puente "
                "USB: si el disco se conecta con otro adaptador, la tabla MBR "
                "puede volverse ilegible. No mover el disco de carcasa.")
        for p in partitions(disk):
            start, size = _int(p.get("start")), _int(p.get("size"))
            if start is None or size is None:
                add(BLOCK, "B07", f"{p.get('path')}: sin START/SIZE; no se "
                    "puede verificar el límite MBR.")
                continue
            if start + size // ls > MBR_MAX_SECTORS:
                add(BLOCK, "B07", f"{p.get('path')} termina más allá del "
                    "límite de 2^32 sectores de MBR.")
    # ESP.
    esp_rec = None
    if uefi:
        if not esp_path:
            add(BLOCK, "B08", "No se indicó la ESP del Seagate (--esp).")
        else:
            edisk, epart = find_part(tree, esp_path)
            if epart is None:
                add(BLOCK, "B08", f"La ESP {esp_path} no existe.")
            elif edisk is not disk:
                add(BLOCK, "B08", f"La ESP {esp_path} está en OTRO disco "
                    f"({edisk.get('path')}). Nunca usar la ESP de Windows.")
            elif epart is part:
                add(BLOCK, "B08", "La ESP y la raíz no pueden ser la misma "
                    "partición.")
            elif not is_esp(epart):
                add(BLOCK, "B08", f"{esp_path} no es una ESP real (tipo "
                    f"{epart.get('parttype')}, fs {epart.get('fstype')}).")
            else:
                if mounted_anywhere(epart):
                    add(BLOCK, "B04", f"La ESP {esp_path} está montada.")
                esp_rec = part_record(epart)
                if not esp_rec["partuuid"]:
                    add(BLOCK, "B11", "La ESP no tiene PARTUUID.")
    # Otras particiones del mismo disco: aviso explícito del riesgo.
    siblings = [p for p in partitions(disk)
                if p is not part and (esp_rec is None
                                      or p.get("path") != esp_path)]
    if siblings:
        add(WARN, "W09", f"El disco destino tiene {len(siblings)} partición(es) "
            "más. El kernel no puede impedir al 100 % que un particionador "
            "las borre mientras el disco esté desbloqueado: respaldo "
            "verificado obligatorio.")
    if any(lv == BLOCK for lv, _, _ in f):
        return f, None
    allow = {
        "schema": SCHEMA,
        "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "boot_mode": "uefi" if uefi else "bios",
        "disk": ident,
        "target": rec,
        "esp": esp_rec,
        "siblings": [part_record(p) for p in siblings],
    }
    return f, allow


def resolve_allowlisted_disk(tree, allow):
    """Localiza el disco autorizado por identidad, nunca por /dev/sdX.

    Devuelve el nodo del disco o lanza StorageError (fail-closed) si no hay
    exactamente una coincidencia o si las particiones autorizadas cambiaron.
    """
    if allow.get("schema") != SCHEMA:
        raise StorageError("allowlist con versión de esquema desconocida")
    want = allow["disk"]
    matches = [d for d in disks(tree) if same_identity(want, identity(d))]
    if len(matches) != 1:
        raise StorageError(f"se esperaba 1 disco autorizado y hay "
                           f"{len(matches)}: cancelar")
    disk = matches[0]
    by_uuid = {(p.get("partuuid") or "").lower(): p for p in partitions(disk)}
    for key in ("target", "esp"):
        rec = allow.get(key)
        if rec is None:
            if key == "esp" and allow.get("boot_mode") != "uefi":
                continue
            raise StorageError(f"allowlist sin '{key}'")
        p = by_uuid.get(rec["partuuid"])
        if p is None:
            raise StorageError(f"la partición {key} autorizada ya no existe")
        if _int(p.get("size")) != rec["size"] or _int(p.get("start")) != rec["start"]:
            raise StorageError(f"la partición {key} cambió de tamaño/posición")
    return disk


def load_allowlist(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
