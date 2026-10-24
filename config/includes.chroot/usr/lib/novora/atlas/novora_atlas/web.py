"""Servidor web local de ATLAS (solo 127.0.0.1).

Seguridad:
  * escucha solo en 127.0.0.1;
  * toda llamada /api exige la cabecera X-Atlas-Token (secreto aleatorio por
    sesión, en ~/.local/state/novora-atlas/web.json con permisos 0600);
  * se rechaza Host distinto de 127.0.0.1/localhost (DNS rebinding) y Origin
    ajeno (otra web abierta en el navegador no puede usar ATLAS);
  * cuerpos JSON de 1 MiB como máximo.
"""
import hmac
import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config as cfgmod
from . import engine as eng
from . import memoria, screen, store
from .assistant import Assistant
from .ui import PAGE

MAX_BODY = 1 << 20
KINDS = {"notas", "tareas"}


class AtlasServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port, assistant, token, idle):
        super().__init__(("127.0.0.1", port), Handler)
        self.assistant, self.token, self.idle = assistant, token, idle
        self.last = time.time()
        self.allowed_hosts = {f"127.0.0.1:{self.server_port}", f"localhost:{self.server_port}"}


class Handler(BaseHTTPRequestHandler):
    server_version = "NOVORA-ATLAS"
    sys_version = ""

    def log_message(self, fmt, *args):   # sin registro de contenido
        pass

    # --- utilidades --------------------------------------------------
    def _send(self, code, obj=None, ctype="application/json", raw=None):
        body = raw if raw is not None else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; script-src 'self' 'unsafe-inline'; "
                         "style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; "
                         "frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _guard(self, api):
        self.server.last = time.time()
        if self.headers.get("Host", "") not in self.server.allowed_hosts:
            self._send(403, {"error": "host no permitido"})
            return False
        origin = self.headers.get("Origin")
        if origin and origin.replace("http://", "") not in self.server.allowed_hosts:
            self._send(403, {"error": "origen no permitido"})
            return False
        if api:
            tok = self.headers.get("X-Atlas-Token", "")
            if not hmac.compare_digest(tok.encode(), self.server.token.encode()):
                self._send(401, {"error": "token inválido"})
                return False
        return True

    def _json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("cuerpo demasiado grande")
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            raise ValueError("se espera application/json")
        data = json.loads(self.rfile.read(n) or b"{}")
        if not isinstance(data, dict):
            raise ValueError("se espera un objeto JSON")
        return data

    # --- rutas -------------------------------------------------------
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            if self._guard(api=False):
                self._send(200, ctype="text/html", raw=PAGE.encode())
            return
        if not self._guard(api=True):
            return
        a = self.server.assistant
        if self.path == "/api/estado":
            cfg = a.engine.cfg
            self._send(200, {"modelos": [os.path.basename(m) for m in eng.find_models(cfg)],
                             "vision": a.engine.vision, "motor_activo": a.engine.healthy(0.5),
                             "nube_disponible": bool(a.cloud and a.cloud.configured)})
        elif self.path == "/api/skills":
            self._send(200, [{"nombre": x.name, "descripcion": x.description[:200], "origen": x.origin}
                             for x in sorted(a.skills.values(), key=lambda x: x.name)])
        elif self.path == "/api/memoria":
            self._send(200, memoria.stats())
        elif self.path.startswith("/api/") and self.path[5:] in KINDS:
            self._send(200, store.list_items(self.path[5:]))
        else:
            self._send(404, {"error": "no encontrado"})

    def do_POST(self):
        if not self._guard(api=True):
            return
        a = self.server.assistant
        try:
            d = self._json()
            p = self.path
            nube = d.get("nube") is True
            if p == "/api/chat":
                out = a.chat(str(d.get("texto", "")), nube=nube)
            elif p == "/api/pantalla":
                out = a.look_at_screen(str(d.get("pregunta", "")), bool(d.get("region")),
                                       max(0, min(int(d.get("espera_ms") or 0), 10000)),
                                       d.get("captura") or None, nube=nube)
            elif p == "/api/archivo":
                out = a.explain_file(str(d.get("ruta", "")), str(d.get("pregunta", "")), nube=nube)
            elif p == "/api/organizar":
                out = a.organize(nube=nube)
            elif p == "/api/agente":
                out = a.agent(str(d.get("tarea", "")), nube=nube)
            elif p == "/api/investigar":
                out = a.research(str(d.get("pregunta", "")), nube=nube)
            elif p == "/api/resumen":
                out = a.digest(nube=nube)
            elif p == "/api/memoria/indexar":
                rutas = d.get("rutas")
                if not isinstance(rutas, list) or not rutas or not all(isinstance(r, str) for r in rutas):
                    raise ValueError("se espera una lista de rutas")
                out = memoria.index(rutas[:20])
            elif p == "/api/memoria/buscar":
                out = memoria.search(str(d.get("consulta", "")), k=8)
            elif p == "/api/reiniciar":
                a.reset()
                out = {"ok": True}
            elif p == "/api/orden/proponer":
                out = a.propose(str(d.get("orden", "")))
            elif p == "/api/orden/ejecutar":
                out = a.run_confirmed(str(d.get("confirmacion", "")))
            elif p.startswith("/api/") and p[5:] in KINDS:
                out = store.add(p[5:], d.get("texto"), d.get("fecha"))
            elif p.startswith("/api/") and p.count("/") == 3 and p.split("/")[2] in KINDS:
                kind, action = p.split("/")[2], p.split("/")[3]
                if action == "hecho":
                    out = store.set_done(kind, str(d.get("id")), d.get("hecho", True))
                elif action == "borrar":
                    store.remove(kind, str(d.get("id")))
                    out = {"ok": True}
                else:
                    return self._send(404, {"error": "no encontrado"})
            else:
                return self._send(404, {"error": "no encontrado"})
            self._send(200, out)
        except PermissionError as ex:
            self._send(403, {"error": str(ex)})
        except (ValueError, KeyError, FileNotFoundError, memoria.MemoriaError) as ex:
            self._send(400, {"error": str(ex)})
        except (eng.EngineError, screen.ScreenError) as ex:
            self._send(503, {"error": str(ex)})


def state_file():
    return os.path.join(cfgmod.user_dirs()["state"], "web.json")


def serve(cfg=None, port=None, assistant=None):
    cfg = cfg or cfgmod.load()
    token = secrets.token_urlsafe(24)
    srv = AtlasServer(cfg["web_port"] if port is None else port,
                      assistant or Assistant(eng.Engine(cfg)), token,
                      cfg["web_idle_seconds"])
    fd = os.open(state_file(), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump({"port": srv.server_port, "token": token, "pid": os.getpid()}, fh)

    def idle_watch():
        while True:
            time.sleep(10)
            if time.time() - srv.last > srv.idle:
                srv.shutdown()
                return
    threading.Thread(target=idle_watch, daemon=True).start()
    try:
        srv.serve_forever()
    finally:
        srv.assistant.engine.stop()
        try:
            os.remove(state_file())
        except OSError:
            pass
    return srv
