"""Resumen diario y rutinas programadas de ATLAS (todo local).

  * `atlas resumen`: tareas, notas, actualizaciones y espacio libre, redactado
    por la IA local; opcionalmente en voz alta (espeak-ng) y como notificación.
  * `atlas rutina agregar`: programa el resumen o una tarea del agente con un
    temporizador de systemd del USUARIO (sin root). Cada ejecución recuerda el
    resultado anterior para poder comparar ("¿qué cambió desde ayer?").
  * Las rutinas son SIEMPRE locales (nunca modo nube) y su agente solo ejecuta
    órdenes de solo lectura: lo demás queda anotado como pendiente.
"""
import json
import os
import re
import shutil
import subprocess
import time

from . import config as cfgmod
from . import engine as eng
from . import memoria, store

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
HOUR_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
DAYS = {"diario": "*-*-*", "laborables": "Mon..Fri *-*-*", "fin-de-semana": "Sat,Sun *-*-*"}
KEEP = 30


class RutinaError(Exception):
    pass


def _exe(var, default):
    return os.environ.get(var, default)


# --- resumen -------------------------------------------------------------------
def gather():
    today = time.strftime("%Y-%m-%d")
    tasks = [t for t in store.list_items("tareas") if not t["hecho"]]
    late = [t for t in tasks if t.get("fecha") and t["fecha"][:10] < today]
    due = [t for t in tasks if t.get("fecha", "")[:10] == today]
    other = [t for t in tasks if t not in late and t not in due]
    notes = store.list_items("notas")[-10:]
    upd = None
    try:
        r = subprocess.run([_exe("NOVORA_ATLAS_APT", "apt"), "list", "--upgradable"], capture_output=True,
                           text=True, timeout=30, stdin=subprocess.DEVNULL, env={**os.environ, "LANG": "C"})
        if r.returncode == 0:
            upd = sum(1 for line in r.stdout.splitlines() if "/" in line and "[upgradable" in line)
    except (OSError, subprocess.TimeoutExpired):
        pass
    du = shutil.disk_usage(os.path.expanduser("~"))
    mem = memoria.stats()
    return {"fecha": today, "atrasadas": late, "hoy": due, "pendientes": other, "notas": notes,
            "actualizaciones": upd, "libre_gib": round(du.free / 2**30, 1),
            "libre_pct": round(100 * du.free / du.total, 1) if du.total else None,
            "documentos_indexados": mem["documentos"]}


def plain(d):
    def lst(items):
        return "\n".join(f"  - {t['texto']}" + (f" ({t['fecha']})" if t.get("fecha") else "") for t in items)
    parts = [f"Resumen de ATLAS · {d['fecha']}"]
    if d["atrasadas"]:
        parts.append(f"Tareas atrasadas ({len(d['atrasadas'])}):\n{lst(d['atrasadas'])}")
    if d["hoy"]:
        parts.append(f"Para hoy ({len(d['hoy'])}):\n{lst(d['hoy'])}")
    if d["pendientes"]:
        parts.append(f"Otras pendientes ({len(d['pendientes'])}):\n{lst(d['pendientes'][:10])}")
    if not (d["atrasadas"] or d["hoy"] or d["pendientes"]):
        parts.append("No tienes tareas pendientes.")
    if d["actualizaciones"]:
        parts.append(f"Hay {d['actualizaciones']} actualizaciones disponibles (Discover o novora-actualizar).")
    if d["libre_pct"] is not None and d["libre_pct"] < 10:
        parts.append(f"Poco espacio libre en tu carpeta: {d['libre_gib']} GiB ({d['libre_pct']} %).")
    return "\n\n".join(parts)


def digest(assistant, nube=False):
    d = gather()
    base = plain(d)
    notes = "\n".join(f"- {n['texto']}" for n in d["notas"]) or "(sin notas)"
    try:
        engine = assistant._engine_for(nube)
        text = engine.chat([
            {"role": "system", "content": assistant.history[0]["content"]},
            {"role": "user", "content": "Escribe mi resumen del día: breve, cálido y práctico (máx. 12 "
                                        "líneas). Empieza por lo urgente y sugiere el orden del día. "
                                        "Usa solo estos datos:\n<datos origen=\"resumen\">\n"
                                        f"{base}\n\nNotas recientes:\n{notes}\n</datos>"}], max_tokens=600)
        used_ai = True
    except (eng.EngineError, ValueError):
        text, used_ai = base, False
    out = {"respuesta": text.strip(), "datos": d, "ia": used_ai, "ordenes": []}
    if nube:
        out["nube"] = True
    return out


def speak(text):
    exe = shutil.which(_exe("NOVORA_ATLAS_ESPEAK", "espeak-ng"))
    if not exe:
        raise RutinaError("no está instalado espeak-ng (voz local)")
    clean = re.sub(r"[`*#_>\[\]]", "", text)[:4000]
    subprocess.run([exe, "-v", "es-419", "-s", "165", "--", clean], timeout=300,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def notify(title, text):
    exe = shutil.which(_exe("NOVORA_ATLAS_NOTIFY", "notify-send"))
    if exe:
        subprocess.run([exe, "--app-name=ATLAS", "--icon=novora-logo", title, text[:400]],
                       timeout=10, stdin=subprocess.DEVNULL, check=False)


# --- rutinas ---------------------------------------------------------------------
def _file():
    return os.path.join(cfgmod.user_dirs()["data"], "rutinas.json")


def load():
    try:
        with open(_file(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data):
    fd = os.open(_file() + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(_file() + ".tmp", _file())


def unit_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or ""
    base = base if os.path.isabs(base) else os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "systemd", "user")


def _unit(name):
    return f"novora-atlas-rutina-{name}"


def _systemctl(*args):
    exe = _exe("NOVORA_ATLAS_SYSTEMCTL", "systemctl")
    try:
        return subprocess.run([exe, "--user", *args], capture_output=True, text=True, timeout=30,
                              stdin=subprocess.DEVNULL).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def add(name, hora, tipo, instruccion="", dias="diario", voz=False):
    if not NAME_RE.match(name or ""):
        raise RutinaError("nombre no válido: minúsculas, números y guiones (máx. 32)")
    m = HOUR_RE.match(hora or "")
    if not m:
        raise RutinaError("hora no válida (formato HH:MM, por ejemplo 08:30)")
    if tipo not in ("resumen", "agente"):
        raise RutinaError("tipo no válido (resumen o agente)")
    if tipo == "agente" and not (instruccion or "").strip():
        raise RutinaError("la rutina de agente necesita una instrucción")
    if dias not in DAYS:
        raise RutinaError(f"días no válidos ({', '.join(DAYS)})")
    data = load()
    data[name] = {"tipo": tipo, "hora": hora, "dias": dias, "instruccion": (instruccion or "")[:2000],
                  "voz": bool(voz), "creada": time.strftime("%Y-%m-%d %H:%M")}
    _save(data)
    os.makedirs(unit_dir(), exist_ok=True)
    atlas = _exe("NOVORA_ATLAS_BIN", "/usr/local/bin/atlas")
    with open(os.path.join(unit_dir(), _unit(name) + ".service"), "w", encoding="utf-8") as fh:
        fh.write(f"[Unit]\nDescription=ATLAS: rutina {name}\n\n[Service]\nType=oneshot\n"
                 f"ExecStart={atlas} rutina ejecutar {name}\nNice=10\n")
    with open(os.path.join(unit_dir(), _unit(name) + ".timer"), "w", encoding="utf-8") as fh:
        fh.write(f"[Unit]\nDescription=ATLAS: rutina {name} ({dias} {hora})\n\n[Timer]\n"
                 f"OnCalendar={DAYS[dias]} {hora}:00\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n")
    active = _systemctl("daemon-reload") and _systemctl("enable", "--now", _unit(name) + ".timer")
    return {"nombre": name, **data[name], "temporizador_activo": active}


def remove(name):
    data = load()
    if name not in data:
        raise RutinaError(f"no existe la rutina '{name}'")
    _systemctl("disable", "--now", _unit(name) + ".timer")
    for ext in (".service", ".timer"):
        try:
            os.remove(os.path.join(unit_dir(), _unit(name) + ext))
        except OSError:
            pass
    _systemctl("daemon-reload")
    del data[name]
    _save(data)


def results_dir(name):
    return os.path.join(cfgmod.user_dirs()["data"], "rutinas", name)


def last_result(name):
    try:
        with open(os.path.join(results_dir(name), "ultimo.md"), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def execute(name, assistant):
    """Ejecuta una rutina (lo llama el temporizador). Siempre local."""
    from .agente import Agente
    r = load().get(name)
    if not r:
        raise RutinaError(f"no existe la rutina '{name}'")
    if r["tipo"] == "resumen":
        out = digest(assistant)
    else:
        prev = last_result(name)
        ctx = ("Resultado de la ejecución anterior (para comparar y decir qué cambió):\n"
               f"<datos origen=\"rutina-anterior\">\n{prev[:1500]}\n</datos>") if prev else ""
        out = Agente(assistant).run(r["instruccion"], nube=False, extra_context=ctx)
    text = out["respuesta"]
    pend = [o["orden"] for o in out.get("ordenes", []) if o.get("confirmacion")]
    if pend:
        text += "\n\nPendiente de tu confirmación (no se ejecutó):\n" + "\n".join(f"- {p}" for p in pend)
    d = results_dir(name)
    os.makedirs(d, mode=0o700, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H%M")
    for fname in (f"{stamp}.md", "ultimo.md"):
        fd = os.open(os.path.join(d, fname), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(f"# ATLAS · rutina {name} · {stamp}\n\n{text}\n")
    old = sorted(f for f in os.listdir(d) if f != "ultimo.md")
    for f in old[:-KEEP]:
        os.remove(os.path.join(d, f))
    notify(f"ATLAS · {name}", text)
    if r.get("voz"):
        try:
            speak(text)
        except RutinaError:
            pass
    return {"respuesta": text, "archivo": os.path.join(d, f"{stamp}.md")}
