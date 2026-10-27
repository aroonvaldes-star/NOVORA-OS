"""Pruebas del auditor y de la resolución por identidad (sin hardware)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LIB = os.path.join(ROOT, "config/includes.chroot/usr/lib/novora")
AUDIT = os.path.join(ROOT, "config/includes.chroot/usr/local/bin/novora-storage-audit")
sys.path.insert(0, LIB)
sys.path.insert(0, os.path.join(HERE, "fixtures"))
import make_fixtures  # noqa: E402
import novora_storage as ns  # noqa: E402

FX = tempfile.mkdtemp(prefix="novora-fx-")
make_fixtures.write_all(FX)


def tree(name):
    return ns.load_tree(os.path.join(FX, f"{name}.json"))


def codes(findings, level=ns.BLOCK):
    return {c for lv, c, _ in findings if lv == level}


class Evaluate(unittest.TestCase):
    def test_valid_seagate_selection_is_approved_with_warnings(self):
        f, allow = ns.evaluate(tree("base"), "/dev/sdb3", "/dev/sdb2", True)
        self.assertEqual(codes(f), set(), f)
        self.assertIn("W07", codes(f, ns.WARN))   # 4 TB en MBR
        self.assertIn("W09", codes(f, ns.WARN))   # hermana NTFS en riesgo
        self.assertEqual(allow["target"]["partuuid"], "5eaga7e0-03")
        self.assertEqual(allow["esp"]["partuuid"], "5eaga7e0-02")

    def test_internal_windows_partition_blocked(self):
        f, allow = ns.evaluate(tree("base"), "/dev/nvme0n1p3", "/dev/nvme0n1p1", True)
        self.assertIsNone(allow)
        self.assertTrue({"B01", "B05"} <= codes(f), f)

    def test_windows_esp_with_seagate_root_blocked(self):
        f, allow = ns.evaluate(tree("base"), "/dev/sdb3", "/dev/nvme0n1p1", True)
        self.assertIsNone(allow)
        self.assertIn("B08", codes(f))

    def test_fat_data_partition_is_not_an_esp(self):
        t = tree("base")
        t[1]["children"][1]["parttype"] = "0xc"      # FAT32 normal, no ESP
        f, allow = ns.evaluate(t, "/dev/sdb3", "/dev/sdb2", True)
        self.assertIsNone(allow)
        self.assertIn("B08", codes(f))

    def test_fat32_from_windows_accepted_only_when_asked(self):
        """Disco del usuario: FAT32 0x0c (100 GB) + ext4 (1 TB) creadas en Windows."""
        t = tree("base")
        t[1]["children"][1]["parttype"] = "0xc"
        t[1]["children"][2]["fstype"] = "ext4"
        f, allow = ns.evaluate(t, "/dev/sdb3", "/dev/sdb2", True, allow_fat_esp=True)
        self.assertEqual(codes(f), set(), f)
        self.assertTrue({"W05", "W10"} <= codes(f, ns.WARN), f)
        self.assertEqual(allow["esp"]["parttype"], "0xc")
        t[1]["children"][1]["parttype"] = "0x7"      # NTFS no sirve aunque se pida
        f, allow = ns.evaluate(t, "/dev/sdb3", "/dev/sdb2", True, allow_fat_esp=True)
        self.assertIsNone(allow)
        f, allow = ns.evaluate(tree("base"), "/dev/sdb3", "/dev/nvme0n1p1", True, allow_fat_esp=True)
        self.assertIn("B08", codes(f))                # nunca la de Windows

    def test_ntfs_data_partition_blocked(self):
        f, allow = ns.evaluate(tree("base"), "/dev/sdb1", "/dev/sdb2", True)
        self.assertIsNone(allow)
        self.assertIn("B05", codes(f))

    def test_missing_serial_blocked(self):
        f, allow = ns.evaluate(tree("no_serial"), "/dev/sdb3", "/dev/sdb2", True)
        self.assertIsNone(allow)
        self.assertIn("B02", codes(f))

    def test_identical_twin_disks_blocked(self):
        f, allow = ns.evaluate(tree("twins"), "/dev/sdb3", "/dev/sdb2", True)
        self.assertIsNone(allow)
        self.assertIn("B10", codes(f))

    def test_live_medium_blocked(self):
        f, allow = ns.evaluate(tree("base"), "/dev/sdc1", None, True)
        self.assertIsNone(allow)
        self.assertIn("B03", codes(f))

    def test_mounted_through_luks_child_blocked(self):
        f, allow = ns.evaluate(tree("luks_mounted"), "/dev/sdb3", "/dev/sdb2", True)
        self.assertIsNone(allow)
        self.assertTrue({"B04", "B05"} <= codes(f), f)

    def test_partition_beyond_mbr_limit_blocked(self):
        f, allow = ns.evaluate(tree("mbr_beyond"), "/dev/sdb3", "/dev/sdb2", True)
        self.assertIsNone(allow)
        self.assertIn("B07", codes(f))

    def test_4k_logical_sector_warns(self):
        f, _ = ns.evaluate(tree("logsec4k"), "/dev/sdb3", "/dev/sdb2", True)
        self.assertIn("W08", codes(f, ns.WARN))

    def test_bios_boot_blocked(self):
        f, allow = ns.evaluate(tree("base"), "/dev/sdb3", None, False)
        self.assertIsNone(allow)
        self.assertIn("B13", codes(f))

    def test_unknown_filesystem_fail_closed(self):
        t = tree("base")
        t[1]["children"][2]["fstype"] = "fs_inventado"
        f, allow = ns.evaluate(t, "/dev/sdb3", "/dev/sdb2", True)
        self.assertIsNone(allow)


class Resolve(unittest.TestCase):
    def setUp(self):
        _, self.allow = ns.evaluate(tree("base"), "/dev/sdb3", "/dev/sdb2", True)

    def test_T05_resolves_by_identity_after_sdX_swap(self):
        d = ns.resolve_allowlisted_disk(tree("swapped"), self.allow)
        self.assertEqual(d["path"], "/dev/sdd")

    def test_T06_unplugged_fails_closed(self):
        with self.assertRaises(ns.StorageError):
            ns.resolve_allowlisted_disk(tree("unplugged"), self.allow)

    def test_twins_fail_closed(self):
        with self.assertRaises(ns.StorageError):
            ns.resolve_allowlisted_disk(tree("twins"), self.allow)

    def test_resized_partition_fails_closed(self):
        with self.assertRaises(ns.StorageError):
            ns.resolve_allowlisted_disk(tree("resized"), self.allow)

    def test_identity_requires_serial_or_wwn(self):
        a = dict(self.allow, disk=dict(self.allow["disk"], serial=None, wwn=None))
        with self.assertRaises(ns.StorageError):
            ns.resolve_allowlisted_disk(tree("base"), a)


class Cli(unittest.TestCase):
    def run_cli(self, *args):
        env = dict(os.environ, NOVORA_LIB=LIB)
        return subprocess.run([sys.executable, "-I", AUDIT, *args], env=env,
                              capture_output=True, text=True)

    def test_listing_is_read_only_and_masks_serial(self):
        r = self.run_cli("--lsblk-json", os.path.join(FX, "base.json"), "--assume-uefi")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("SEAGSER0042", r.stdout)
        self.assertIn("…0042", r.stdout)

    def test_blocked_selection_exit_3_and_no_allowlist(self):
        out = os.path.join(FX, "allow-blocked.json")
        r = self.run_cli("--lsblk-json", os.path.join(FX, "base.json"), "--assume-uefi",
                         "--target", "/dev/nvme0n1p3", "--esp", "/dev/nvme0n1p1",
                         "--emit-allowlist", out)
        self.assertEqual(r.returncode, 3)
        self.assertFalse(os.path.exists(out))

    def test_approved_selection_writes_private_allowlist(self):
        out = os.path.join(FX, "allow-ok.json")
        r = self.run_cli("--lsblk-json", os.path.join(FX, "base.json"), "--assume-uefi",
                         "--target", "/dev/sdb3", "--esp", "/dev/sdb2",
                         "--emit-allowlist", out)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(os.stat(out).st_mode & 0o777, 0o600)
        with open(out, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["target"]["partuuid"], "5eaga7e0-03")

    def test_interactive_eof_cancels(self):
        r = subprocess.run([sys.executable, "-I", AUDIT, "--lsblk-json",
                            os.path.join(FX, "base.json"), "--assume-uefi", "--interactive"],
                           env=dict(os.environ, NOVORA_LIB=LIB), input="",
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)


class GuardSysfs(unittest.TestCase):
    """La enumeración por sysfs no depende de lsblk y omite loop/zram/sr/dm."""
    def test_sysfs_enumeration(self):
        import importlib.machinery
        import importlib.util
        d = tempfile.mkdtemp()
        for n in ("sda", "sda1", "nvme0n1", "nvme0n1p1", "loop0", "zram0", "sr0", "dm-0", "mmcblk0"):
            os.mkdir(os.path.join(d, n))
        os.environ["NOVORA_SYSFS_BLOCK"] = d
        os.environ.pop("NOVORA_TEST_NO_SYSFS", None)
        os.environ["NOVORA_LIB"] = LIB
        path = os.path.join(ROOT, "config/includes.chroot/usr/local/sbin/novora-disk-guard")
        loader = importlib.machinery.SourceFileLoader("novora_disk_guard", path)
        spec = importlib.util.spec_from_loader("novora_disk_guard", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        self.assertEqual(mod.sysfs_nodes(), ["/dev/mmcblk0", "/dev/nvme0n1", "/dev/nvme0n1p1",
                                             "/dev/sda", "/dev/sda1"])


def load_guard():
    import importlib.machinery
    import importlib.util
    os.environ["NOVORA_LIB"] = LIB
    path = os.path.join(ROOT, "config/includes.chroot/usr/local/sbin/novora-disk-guard")
    loader = importlib.machinery.SourceFileLoader("novora_disk_guard", path)
    spec = importlib.util.spec_from_loader("novora_disk_guard", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class GuardStacked(unittest.TestCase):
    """R-05: capas dm/LVM/MD activas antes del bloqueo → fail-closed."""
    def setUp(self):
        self.sys = tempfile.mkdtemp()
        for n in ("sdb", "sdb1", "sdb2", "sdb3", "nvme0n1", "nvme0n1p1", "nvme0n1p2",
                  "nvme0n1p3", "dm-0", "dm-1"):
            os.makedirs(os.path.join(self.sys, n, "holders"))
        os.environ["NOVORA_SYSFS_BLOCK"] = self.sys
        os.environ["NOVORA_TEST_NO_SYSFS"] = "1"
        os.environ["NOVORA_STATE_DIR"] = tempfile.mkdtemp()
        self.mounts = os.path.join(self.sys, "mounts")
        with open(self.mounts, "w") as fh:
            fh.write("proc /proc proc rw 0 0\n")
        os.environ["NOVORA_MOUNTS"] = self.mounts
        self.g = load_guard()
        self.calls = []
        self.g.set_ro = lambda node, ro: self.calls.append((node, ro))
        self.g.efivars_ro = lambda: True

    def tearDown(self):
        for k in ("NOVORA_SYSFS_BLOCK", "NOVORA_MOUNTS", "NOVORA_TEST_NO_SYSFS"):
            os.environ.pop(k, None)

    def hold(self, lower, upper):
        os.mkdir(os.path.join(self.sys, lower, "holders", upper))

    def test_holders_are_followed_recursively(self):
        self.hold("nvme0n1p3", "dm-0")        # LUKS abierto
        self.hold("dm-0", "dm-1")             # LVM encima
        self.assertEqual(self.g.holders("/dev/nvme0n1p3"), ["/dev/dm-0", "/dev/dm-1"])
        self.assertEqual(self.g.holders("/dev/sdb1"), [])

    def test_lockdown_fails_closed_with_active_layers(self):
        self.assertEqual(self.g.cmd_lockdown(tree("base")), 0)
        self.hold("nvme0n1p3", "dm-0")
        self.calls.clear()
        self.assertEqual(self.g.cmd_lockdown(tree("base")), 4)
        self.assertIn(("/dev/dm-0", True), self.calls)     # la capa también queda RO

    def test_rw_mount_through_mapper_detected(self):
        with open(self.mounts, "a") as fh:
            fh.write("/dev/mapper/vg-datos /mnt ext4 rw,relatime 0 0\n")
        disk = next(d for d in ns.disks(tree("base")) if d["path"] == "/dev/nvme0n1")
        self.assertEqual(self.g.rw_mounts(disk), [])
        self.assertEqual(self.g.rw_mounts(disk, ["/dev/mapper/vg-datos"]),
                         [("/dev/mapper/vg-datos", "/mnt")])

    def test_unlock_and_verify_refuse_layers_on_protected_disks(self):
        f, allow = ns.evaluate(tree("base"), "/dev/sdb3", "/dev/sdb2", True)
        self.hold("nvme0n1p3", "dm-0")
        os.environ["NOVORA_LSBLK_JSON"] = os.path.join(FX, "base.json")
        try:
            self.assertEqual(self.g.cmd_unlock(tree("base"), allow, True), 4)
            self.assertFalse(any(ro is False for _, ro in self.calls), self.calls)
            self.assertEqual(self.g.cmd_verify(tree("base"), allow), 5)
        finally:
            del os.environ["NOVORA_LSBLK_JSON"]


if __name__ == "__main__":
    unittest.main(verbosity=2)
