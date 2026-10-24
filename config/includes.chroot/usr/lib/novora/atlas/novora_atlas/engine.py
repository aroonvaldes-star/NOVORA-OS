"""Motor de lenguaje local: arranca llama-server bajo demanda y lo detiene
tras un tiempo sin uso para liberar RAM/VRAM. Sin internet."""
import base64
import glob
import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from . import config as cfgmod


class EngineError(Exception):
    pass


def find_models(cfg):
    found = []
    for d in cfg["models_dirs"]:
        found += sorted(glob.glob(os.path.join(d, "*.gguf")))
    return [m for m in found if "mmproj" not in os.path.basename(m).lower()]


def find_mmproj(cfg):
    if cfg.get("vision_mmproj"):
        for d in cfg["models_dirs"]:
            p = os.path.join(d, cfg["vision_mmproj"])
            if os.path.isfile(p):
                return p
        return None
    for d in cfg["models_dirs"]:
        hits = sorted(glob.glob(os.path.join(d, "*mmproj*.gguf")))
        if hits:
            return hits[0]
    return None


def pick_model(cfg):
    models = find_models(cfg)
    if cfg.get("chat_model"):
        models = [m for m in models if os.path.basename(m) == cfg["chat_model"]]
    if not models:
        raise EngineError(
            "No hay ningún modelo instalado. Copia un archivo .gguf con:\n"
            "  atlas modelo instalar /ruta/al/modelo.gguf\n"
            "(no hace falta internet si lo traes en una memoria USB)")
    return models[0]


def pid_file():
    return os.path.join(cfgmod.user_dirs()["state"], "motor.pid")


def _remove_pid():
    try:
        os.remove(pid_file())
    except OSError:
        pass


def stop_detached(endpoint):
    """Detiene un motor iniciado por `atlas motor iniciar`. Solo actúa si el PID
    guardado sigue siendo un servidor lanzado por ATLAS (escucha en 127.0.0.1 y
    en el puerto configurado); si no, no toca ningún proceso."""
    try:
        with open(pid_file(), encoding="ascii") as fh:
            pid = int(fh.read().strip())
    except (OSError, ValueError):
        return False
    port = str(urlparse(endpoint).port or 8181)
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            args = [a.decode(errors="replace") for a in fh.read().split(b"\0") if a]
    except OSError:
        _remove_pid()
        return False
    ours = any(args[i:i + 2] == ["--host", "127.0.0.1"] for i in range(len(args))) and \
        any(args[i:i + 2] == ["--port", port] for i in range(len(args)))
    if not ours:
        _remove_pid()
        return False
    import signal
    os.kill(pid, signal.SIGTERM)
    _remove_pid()
    return True


class Engine:
    def __init__(self, cfg=None):
        self.cfg = cfg or cfgmod.load()
        self.base = self.cfg["endpoint"].rstrip("/")
        self.proc = None
        self.last_use = 0.0
        self.lock = threading.Lock()
        self._watch = None

    # ---- servidor -------------------------------------------------------
    def healthy(self, timeout=1.5):
        try:
            with urllib.request.urlopen(self.base + "/health", timeout=timeout) as r:
                return r.status == 200
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def ensure_running(self):
        with self.lock:
            self.last_use = time.time()
            if self.healthy():
                return
            if not self.cfg["manage_server"]:
                raise EngineError(f"El motor local no responde en {self.base}")
            model = pick_model(self.cfg)
            port = str(urlparse(self.base).port or 8181)
            argv = [self.cfg["server_binary"], "-m", model, "--host", "127.0.0.1",
                    "--port", port, "-c", str(self.cfg["context"]),
                    "-ngl", str(self.cfg["gpu_layers"]),
                    "--alias", "novora-atlas"]     # nombre estable para otras apps (p. ej. GenOffice)
            mm = find_mmproj(self.cfg)
            if mm:
                argv += ["--mmproj", mm]
            log = open(os.path.join(cfgmod.user_dirs()["state"], "llama-server.log"), "ab")
            try:
                self.proc = subprocess.Popen(argv, stdout=log, stderr=log,
                                             stdin=subprocess.DEVNULL,
                                             start_new_session=True)
            except FileNotFoundError as ex:
                raise EngineError("No está instalado llama-server (paquete "
                                  "llama.cpp-tools).") from ex
            finally:
                log.close()
            try:
                with open(pid_file(), "w", encoding="ascii") as fh:
                    fh.write(str(self.proc.pid))
            except OSError:
                pass
            deadline = time.time() + 180
            while time.time() < deadline:
                if self.proc.poll() is not None:
                    raise EngineError("llama-server terminó al arrancar; revisa "
                                      "~/.local/state/novora-atlas/llama-server.log")
                if self.healthy():
                    break
                time.sleep(0.5)
            else:
                self.stop()
                raise EngineError("llama-server no respondió en 180 s")
            if self._watch is None:
                self._watch = threading.Thread(target=self._idle_watch, daemon=True)
                self._watch.start()

    def _idle_watch(self):
        while True:
            time.sleep(5)
            idle = time.time() - self.last_use
            if self.proc and self.proc.poll() is None and idle > self.cfg["server_idle_seconds"]:
                self.stop()

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            _remove_pid()
        self.proc = None

    @property
    def vision(self):
        return find_mmproj(self.cfg) is not None

    # ---- inferencia -----------------------------------------------------
    def chat(self, messages, max_tokens=800, temperature=0.3):
        self.ensure_running()
        body = json.dumps({"model": "novora-atlas", "messages": messages,
                           "max_tokens": max_tokens, "temperature": temperature,
                           "stream": False}).encode()
        req = urllib.request.Request(self.base + "/v1/chat/completions", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                data = json.load(r)
        except (urllib.error.URLError, OSError, ValueError) as ex:
            raise EngineError(f"Error del motor local: {ex}") from ex
        finally:
            self.last_use = time.time()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as ex:
            raise EngineError("Respuesta del motor sin contenido") from ex


class CloudEngine:
    """Modo nube: API compatible con OpenAI de una pasarela LOCAL (OmniRoute),
    que reenvía a los proveedores que tú configuraste en ella."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.base = cfg["nube_endpoint"].rstrip("/")
        try:
            with open(cfgmod.nube_key_path(), encoding="utf-8") as fh:
                self.key = fh.read().strip()
        except OSError:
            self.key = ""
        self.vision = False

    @property
    def configured(self):
        return bool(self.base and self.key)

    def healthy(self, timeout=2):
        req = urllib.request.Request(self.base + "/models",
                                     headers={"Authorization": "Bearer " + self.key})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status == 200
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def chat(self, messages, max_tokens=1500, temperature=0.3):
        if not self.configured:
            raise EngineError("Modo nube no configurado: atlas nube activar")
        body = json.dumps({"model": self.cfg.get("nube_modelo", "auto"), "messages": messages,
                           "max_tokens": max_tokens, "temperature": temperature,
                           "stream": False}).encode()
        req = urllib.request.Request(self.base + "/chat/completions", data=body,
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Bearer " + self.key})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                data = json.load(r)
            return data["choices"][0]["message"]["content"].strip()
        except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError, TypeError) as ex:
            raise EngineError(f"La pasarela de nube no respondió bien: {ex}") from ex

    def stop(self):
        pass


def image_part(path):
    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    return {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}}
