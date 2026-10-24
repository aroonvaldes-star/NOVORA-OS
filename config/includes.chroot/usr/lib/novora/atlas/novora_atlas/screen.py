"""Captura de pantalla y OCR locales.

En Plasma 6 (Wayland) Spectacle está autorizado por KWin para capturar; la
captura solo ocurre cuando el usuario la pide (botón, atajo u orden), y la
imagen se guarda en el directorio de estado del usuario (0700) y se borra
después de analizarla.
"""
import os
import re
import shutil
import subprocess
import tempfile
import time

from . import config as cfgmod


class ScreenError(Exception):
    pass


def capture(region=False, delay_ms=0):
    tool = os.environ.get("NOVORA_ATLAS_SPECTACLE", "spectacle")
    if not shutil.which(tool):
        raise ScreenError("Spectacle no está instalado; no puedo ver la pantalla.")
    fd, path = tempfile.mkstemp(prefix="pantalla-", suffix=".png",
                                dir=cfgmod.user_dirs()["state"])
    os.close(fd)
    os.remove(path)
    mode = "--region" if region else "--fullscreen"
    argv = [tool, "--background", "--nonotify", mode, "--output", path]
    if delay_ms:
        argv += ["--delay", str(int(delay_ms))]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=60 + delay_ms // 1000)
    for _ in range(20):
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
        time.sleep(0.1)
    raise ScreenError(f"La captura falló: {r.stderr.strip() or 'sin imagen'}")


CAPTURE_RE = re.compile(r"^pantalla-[A-Za-z0-9_]+\.png$")


def capture_by_id(capture_id):
    """Ruta de una captura previa hecha por ATLAS (solo su directorio)."""
    if not CAPTURE_RE.match(capture_id or ""):
        raise ScreenError("identificador de captura no válido")
    path = os.path.join(cfgmod.user_dirs()["state"], capture_id)
    if not os.path.isfile(path) or os.path.islink(path):
        raise ScreenError("la captura ya no existe")
    return path


def ocr(path, langs="spa+eng"):
    tool = os.environ.get("NOVORA_ATLAS_TESSERACT", "tesseract")
    if not shutil.which(tool):
        return ""
    r = subprocess.run([tool, path, "-", "-l", langs], capture_output=True,
                       text=True, timeout=120)
    if r.returncode != 0:
        r = subprocess.run([tool, path, "-"], capture_output=True, text=True,
                           timeout=120)
    return r.stdout.strip()[:12000]


def discard(path):
    try:
        os.remove(path)
    except OSError:
        pass
