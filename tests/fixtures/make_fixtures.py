"""Genera árboles lsblk sintéticos (sin seriales reales) para las pruebas."""
import copy
import json
import os

TiB, GiB, MiB = 1024 ** 4, 1024 ** 3, 1024 ** 2
ESP_GPT = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"
MSR = "e3c9e316-0b5c-4db8-817d-f92df00215ae"
BASIC = "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7"


def part(path, size, start, fstype=None, parttype=None, partuuid=None,
         mounts=None, children=None):
    return {"name": os.path.basename(path), "path": path, "type": "part",
            "size": size, "start": start, "fstype": fstype,
            "parttype": parttype, "partuuid": partuuid,
            "mountpoints": mounts or [None], "children": children or []}


def disk(path, size, model, serial, wwn, tran, pttype, ptuuid, parts,
         log_sec=512):
    return {"name": os.path.basename(path), "path": path, "type": "disk",
            "size": size, "model": model, "serial": serial, "wwn": wwn,
            "tran": tran, "pttype": pttype, "ptuuid": ptuuid,
            "log-sec": log_sec, "phy-sec": 4096, "mountpoints": [None],
            "children": parts}


def windows(path="/dev/nvme0n1", p="p"):
    return disk(path, 512 * GiB, "NVMe SIMULADO", "WINSER0001", "eui.0001",
                "nvme", "gpt", "aaaa0000-0000-0000-0000-000000000001", [
                    part(f"{path}{p}1", 100 * MiB, 2048, "vfat", ESP_GPT,
                         "aaaa0001-0000-0000-0000-000000000001"),
                    part(f"{path}{p}2", 16 * MiB, 206848, None, MSR,
                         "aaaa0002-0000-0000-0000-000000000002"),
                    part(f"{path}{p}3", 500 * GiB, 239616, "BitLocker", BASIC,
                         "aaaa0003-0000-0000-0000-000000000003"),
                ])


def seagate_mbr(path="/dev/sdb", serial="SEAGSER0042", log_sec=512):
    """Seagate 4 TB MBR: datos NTFS, ESP FAT32 (0xef) y destino vacío."""
    ls = log_sec
    s = lambda b: b // ls  # noqa: E731  bytes -> sectores
    return disk(path, 4000787030016, "Expansion HDD", serial, None, "usb",
                "dos", "5eaga7e0", [
                    part(f"{path}1", 1500 * GiB, s(MiB), "ntfs", "0x7",
                         "5eaga7e0-01"),
                    part(f"{path}2", 512 * MiB, s(MiB + 1500 * GiB), "vfat",
                         "0xef", "5eaga7e0-02"),
                    part(f"{path}3", 100 * GiB, s(2 * MiB + 1500 * GiB + 512 * MiB),
                         None, "0x83", "5eaga7e0-03"),
                ], log_sec=log_sec)


def live_usb(path="/dev/sdc"):
    return disk(path, 32 * GiB, "USB STICK", "LIVESER77", None, "usb", "dos",
                "11ve0000", [part(f"{path}1", 4 * GiB, 0, "iso9660", "0x0",
                                  "11ve0000-01", ["/run/live/medium"])])


def tree(*disks):
    return {"blockdevices": list(disks)}


def write_all(outdir):
    os.makedirs(outdir, exist_ok=True)
    fx = {
        "base": tree(windows(), seagate_mbr(), live_usb()),
        # T05: mismos discos, rutas intercambiadas (sdb <-> sdd) y otro orden.
        "swapped": tree(live_usb("/dev/sdb"), seagate_mbr("/dev/sdd"), windows()),
        # T06: Seagate desconectado.
        "unplugged": tree(windows(), live_usb()),
        "no_serial": tree(windows(), seagate_mbr(serial=None), live_usb()),
        "twins": tree(windows(), seagate_mbr(), seagate_mbr("/dev/sdd",
                                                            serial="SEAGSER0042")),
        "logsec4k": tree(windows(), seagate_mbr(log_sec=4096)),
    }
    # Partición destino ya formateada y montada a través de LUKS.
    luks = copy.deepcopy(fx["base"])
    tgt = luks["blockdevices"][1]["children"][2]
    tgt["fstype"] = "crypto_LUKS"
    tgt["children"] = [{"name": "luks-x", "path": "/dev/mapper/luks-x",
                        "type": "crypt", "fstype": "ext4",
                        "mountpoints": ["/media/user/x"], "children": []}]
    fx["luks_mounted"] = luks
    # Destino que cruza el límite MBR de 2^32 sectores.
    beyond = copy.deepcopy(fx["base"])
    beyond["blockdevices"][1]["children"][2]["start"] = 2 ** 32 - 1000
    fx["mbr_beyond"] = beyond
    # Partición destino redimensionada tras la auditoría.
    resized = copy.deepcopy(fx["base"])
    resized["blockdevices"][1]["children"][2]["size"] = 90 * GiB
    fx["resized"] = resized
    for name, data in fx.items():
        with open(os.path.join(outdir, f"{name}.json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
    return fx


if __name__ == "__main__":
    import sys
    write_all(sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(__file__))
