"""Política de comandos de ATLAS.

Principios (fail-closed):
  * ATLAS nunca ejecuta nada sin confirmación explícita del usuario, salvo
    en modo agente las órdenes de SOLO LECTURA que no tocan archivos ocultos
    (ver agente.auto_runnable; se puede desactivar con agente_auto_lectura).
  * Ciertas órdenes están PROHIBIDAS siempre, aunque el usuario las pida:
    discos, particiones, arranque/EFI, cifrado, elevación de privilegios y
    cualquier forma de esquivar esta lista (intérpretes con -c, envoltorios,
    operadores de shell).
  * Solo se ejecuta UNA orden simple, sin shell (subprocess sin shell=True).
"""
import os
import re
import shlex

ALLOWED, CONFIRM, FORBIDDEN = "SOLO_LECTURA", "CONFIRMAR", "PROHIBIDO"

FORBIDDEN_EXACT = {
    # discos y particiones
    "dd", "wipefs", "parted", "partprobe", "gparted", "fdisk", "sfdisk",
    "cfdisk", "gdisk", "sgdisk", "cgdisk", "mke2fs", "mkswap", "mkdosfs",
    "blockdev", "hdparm", "sdparm", "nvme", "badblocks", "e2fsck", "fsck",
    "tune2fs", "resize2fs", "ntfsfix", "ntfsresize", "shred", "blkdiscard",
    "losetup", "dmsetup", "mdadm", "cryptsetup", "lvm", "mount", "umount",
    "swapon", "swapoff", "zpool", "zfs", "btrfs", "xfs_repair", "partx",
    "kpartx", "udisksctl", "smartctl",
    # arranque / firmware
    "efibootmgr", "grub-install", "grub-mkconfig", "update-grub", "bootctl",
    "mokutil", "sbctl", "fwupdmgr", "flashrom", "efivar", "kexec",
    "shutdown", "reboot", "poweroff", "halt", "init", "telinit",
    # privilegios y sistema
    "sudo", "su", "pkexec", "doas", "run0", "passwd", "chpasswd", "useradd",
    "userdel", "usermod", "visudo", "systemctl", "service", "modprobe",
    "insmod", "rmmod", "sysctl", "iptables", "nft", "chattr",
    "apt", "apt-get", "dpkg", "flatpak",
    # herramientas NOVORA de seguridad
    "novora-disk-guard", "novora-install", "calamares",
    "novora-gpu", "prime-run", "gamemoderun", "novora-con-ia-local", "npx",  # ejecutan cualquier programa
    # envoltorios que permitirían esquivar la lista
    "env", "xargs", "nohup", "timeout", "nice", "ionice", "chroot",
    "unshare", "nsenter", "setsid", "stdbuf", "script", "watch", "exec",
    "eval", "command", "builtin", "busybox", "strace", "gdb",
    # borrado y permisos masivos
    "rm", "rmdir", "chmod", "chown", "chgrp", "truncate",
}
FORBIDDEN_PREFIXES = ("mkfs", "fsck.", "lv", "vg", "pv", "sg_", "grub-",
                      "zram", "dracut", "update-initramfs", "mkinitramfs")
# Intérpretes: permitidos solo para ejecutar un archivo, nunca código en línea.
INTERPRETERS = {"sh", "bash", "dash", "zsh", "fish", "python", "python3",
                "perl", "ruby", "node", "nodejs", "php", "lua", "tclsh",
                "awk", "gawk", "mawk", "busybox"}
INLINE_FLAGS = {"-c", "-e", "--eval", "-E", "--exec", "-r", "--command"}
READ_ONLY = {"ls", "cat", "head", "tail", "wc", "file", "stat", "pwd",
             "whoami", "date", "uptime", "free", "df", "du", "lsblk", "uname",
             "id", "grep", "rg", "which", "tree", "echo", "printf", "sort",
             "uniq", "diff", "cmp", "sha256sum", "md5sum", "nproc", "lscpu",
             "lsusb", "lspci", "ps"}
PROTECTED_PATH = re.compile(r"(^|[=:,])(/dev/|/sys/|/proc/sys|/boot|/etc|/run/novora)|/dev/")
GIT_READ = {"status", "log", "diff", "show", "branch", "remote", "blame",
            "rev-parse", "describe", "shortlog", "ls-files", "tag"}
SHELL_OPERATORS = re.compile(r"[;&|<>`$(){}\n\\*?\[\]!~]")
FIND_DANGEROUS = {"-exec", "-execdir", "-delete", "-ok", "-okdir", "-fprint",
                  "-fprintf", "-fls"}
# Opciones de programas de READ_ONLY que escriben archivos, cambian el sistema
# o ejecutan otro programa: (letras de opción corta, prefijos de opción larga).
# Con cualquiera de ellas la orden deja de ser de solo lectura → CONFIRMAR.
WRITING_OPTIONS = {
    "sort": ("oT", ("--output", "--compress-program", "--temporary-directory")),
    "tree": ("oRH", ("--output",)),
    "file": ("C", ("--compile",)),
    "date": ("sf", ("--set", "--file")),
    "rg": ("", ("--pre",)),
}
# Opciones globales de git (antes del subcomando): -c, -C, --git-dir,
# --exec-path, --config-env… cambian qué se ejecuta o dónde. Ninguna se
# acepta como solo lectura.
GIT_WRITING_OPTIONS = ("--output", "--ext-diff", "--textconv", "--exec",
                       "--upload-pack", "--receive-pack", "--open-files-in-pager")
# branch, tag y remote solo listan con estas opciones; con un nombre crean,
# borran o renombran.
GIT_LIST_ONLY = {
    "branch": {"-a", "-r", "-v", "-vv", "-l", "--all", "--remotes", "--list",
               "--verbose", "--show-current", "--no-color"},
    "tag": {"-l", "--list", "-n"},
    "remote": {"-v", "--verbose"},
}


class Verdict:
    def __init__(self, level, reason, argv=None):
        self.level, self.reason, self.argv = level, reason, argv or []

    @property
    def runnable(self):
        return self.level in (ALLOWED, CONFIRM)

    def as_dict(self):
        return {"nivel": self.level, "motivo": self.reason, "argv": self.argv}

    def __repr__(self):
        return f"Verdict({self.level}, {self.reason!r})"


def _base(word):
    return os.path.basename(word)


def _writing_option(prog, args):
    """Primera opción de args que hace que un programa de READ_ONLY escriba o
    ejecute algo, o None."""
    short, longs = WRITING_OPTIONS.get(prog, ("", ()))
    for a in args:
        if a == "--":
            break
        if a.startswith("--"):
            if a.split("=", 1)[0].startswith(longs) and longs:
                return a
        elif a.startswith("-") and len(a) > 1 and any(c in short for c in a[1:]):
            return a
    if prog == "uniq":                      # uniq ENTRADA SALIDA escribe SALIDA
        operands = [a for a in args if not a.startswith("-")]
        if len(operands) > 1:
            return operands[1]
    return None


def classify(command):
    """Clasifica una orden propuesta. Nunca la ejecuta."""
    if not isinstance(command, str) or not command.strip():
        return Verdict(FORBIDDEN, "orden vacía")
    if len(command) > 2000:
        return Verdict(FORBIDDEN, "orden demasiado larga")
    if SHELL_OPERATORS.search(command):
        return Verdict(FORBIDDEN, "contiene operadores o comodines de shell "
                       "(; | & > < $ ` * ? ~ …); ATLAS solo ejecuta una orden "
                       "simple. Si la necesitas, ejecútala tú en la terminal.")
    try:
        argv = shlex.split(command)
    except ValueError as ex:
        return Verdict(FORBIDDEN, f"no se pudo analizar: {ex}")
    if not argv:
        return Verdict(FORBIDDEN, "orden vacía")
    prog = _base(argv[0])
    if "=" in argv[0]:
        return Verdict(FORBIDDEN, "asignaciones de variables no permitidas")
    if prog in FORBIDDEN_EXACT or prog.startswith(FORBIDDEN_PREFIXES):
        return Verdict(FORBIDDEN, f"'{prog}' está en la lista prohibida de "
                       "ATLAS (discos, arranque, privilegios o borrado).")
    for a in argv[1:]:
        if PROTECTED_PATH.search(a):
            return Verdict(FORBIDDEN, f"ruta de dispositivos o de sistema "
                           f"protegida ({a})")
    if prog in INTERPRETERS:
        if any(a in INLINE_FLAGS or (a.startswith("-") and not a.startswith("--")
                                     and any(f in a for f in "cer")) for a in argv[1:]):
            return Verdict(FORBIDDEN, f"'{prog}' con código en línea (-c/-e) "
                           "no está permitido")
        if prog in ("awk", "gawk", "mawk"):
            return Verdict(FORBIDDEN, "awk puede ejecutar órdenes (system())")
        if len(argv) < 2:
            return Verdict(FORBIDDEN, f"'{prog}' interactivo no está permitido")
        return Verdict(CONFIRM, f"ejecuta el archivo {argv[1]} con {prog}", argv)
    if prog == "find" and any(a in FIND_DANGEROUS for a in argv[1:]):
        return Verdict(FORBIDDEN, "find con -exec/-delete no está permitido")
    if prog == "git":
        sub = argv[1] if len(argv) > 1 else ""
        if sub.startswith("-"):
            return Verdict(CONFIRM, f"git con opción global {sub} (puede cambiar "
                           "la configuración o el programa que se ejecuta)", argv)
        rest = argv[2:]
        bad = next((a for a in rest if a.split("=", 1)[0] in GIT_WRITING_OPTIONS
                    or (a.startswith("-") and not a.startswith("--") and "O" in a)), None)
        if not bad and sub in GIT_LIST_ONLY:
            bad = next((a for a in rest if a not in GIT_LIST_ONLY[sub]), None)
        if sub in GIT_READ and not bad:
            return Verdict(ALLOWED, f"git {sub} (solo lectura)", argv)
        if bad:
            return Verdict(CONFIRM, f"git {sub} con {bad} puede escribir archivos, "
                           "modificar el repositorio o ejecutar otro programa", argv)
        return Verdict(CONFIRM, f"git {sub or '?'} puede modificar el "
                       "repositorio", argv)
    if prog in ("sed", "perl") and any(a.startswith("-i") for a in argv[1:]):
        return Verdict(CONFIRM, "edita archivos en el lugar", argv)
    if prog in READ_ONLY:
        bad = _writing_option(prog, argv[1:])
        if bad:
            return Verdict(CONFIRM, f"'{prog}' con {bad} escribe archivos, cambia "
                           "el sistema o ejecuta otro programa", argv)
        return Verdict(ALLOWED, f"{prog} (solo lectura)", argv)
    return Verdict(CONFIRM, f"'{prog}' puede modificar archivos o el sistema",
                   argv)
