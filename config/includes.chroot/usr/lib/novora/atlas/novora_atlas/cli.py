"""Línea de órdenes de ATLAS."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

from . import config as cfgmod
from . import engine as eng
from . import memoria, policy, rutinas, screen, store, web
from . import skills as sk
from .assistant import Assistant

C = {"SOLO_LECTURA": "\033[32m", "CONFIRMAR": "\033[33m", "PROHIBIDO": "\033[31m", "": "\033[0m"}


def color(level, text):
    if not sys.stdout.isatty():
        return text
    return C.get(level, "") + text + C[""]


def print_reply(out, assistant, interactive=True):
    text = "\n".join(l for l in out.get("respuesta", "").splitlines() if not l.startswith("ORDEN: "))
    if out.get("nube"):
        print("[☁ respuesta desde la nube vía OmniRoute]")
    if out.get("skill"):
        print(f"[skill: {out['skill']}]")
    for st in out.get("pasos", []):
        args = json.dumps(st["argumentos"], ensure_ascii=False)
        print(f"  · {st['herramienta']} {args[:120]}  →  {st['resultado'].splitlines()[0][:100] if st['resultado'] else ''}")
    if out.get("pasos"):
        print()
    print(text.strip())
    if out.get("aviso"):
        print(f"\n({out['aviso']})")
    if out.get("fuentes"):
        print("\nFuentes:")
        for f in out["fuentes"]:
            print(f"  [{f['n']}] {f['ruta']} (trozo {f['trozo']})")
    for o in out.get("ordenes", []):
        print(color(o["nivel"], f"\n[{o['nivel']}] {o['orden']}") + f"\n  {o['motivo']}")
        if o.get("vista_previa"):
            print("  ┌ vista previa\n" + "\n".join("  │ " + l for l in o["vista_previa"].splitlines()[:25]))
        if o.get("confirmacion") and interactive and sys.stdin.isatty():
            if input("  ¿Ejecutar? escribe 'si' para confirmar: ").strip().lower() == "si":
                r = assistant.run_confirmed(o["confirmacion"])
                print(r["salida"], r["error"], f"(código {r['codigo']})", sep="\n")


def running_web():
    try:
        with open(web.state_file(), encoding="utf-8") as fh:
            st = json.load(fh)
        os.kill(int(st["pid"]), 0)
        req = urllib.request.Request(f"http://127.0.0.1:{st['port']}/api/estado",
                                     headers={"X-Atlas-Token": st["token"],
                                              "Host": f"127.0.0.1:{st['port']}"})
        urllib.request.urlopen(req, timeout=2).close()
        return st
    except (OSError, ValueError, KeyError):
        return None


def cmd_open(args, cfg, extra=""):
    st = running_web()
    if not st:
        subprocess.Popen([sys.executable, "-I", os.path.abspath(sys.argv[0]), "servir"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True,
                         env={**os.environ})
        for _ in range(50):
            time.sleep(0.1)
            st = running_web()
            if st:
                break
    if not st:
        print("No se pudo iniciar el panel de ATLAS.", file=sys.stderr)
        return 1
    url = f"http://127.0.0.1:{st['port']}/#{st['token']}{extra}"
    if args.no_navegador:
        print(url)
        return 0
    opener = shutil.which("xdg-open") or shutil.which("kde-open")
    if not opener:
        print(url)
        return 0
    subprocess.Popen([opener, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return 0


def cmd_model(args, cfg):
    if args.accion == "listar":
        ms = eng.find_models(cfg)
        print("\n".join(ms) if ms else "Sin modelos. Usa: novora-atlas modelo instalar ARCHIVO.gguf")
        mm = eng.find_mmproj(cfg)
        if mm:
            print("Visión:", mm)
        return 0
    src = os.path.abspath(os.path.expanduser(args.ruta or ""))
    if not os.path.isfile(src) or not src.endswith(".gguf"):
        print("Indica un archivo .gguf existente.", file=sys.stderr)
        return 1
    with open(src, "rb") as fh:
        if fh.read(4) != b"GGUF":
            print("El archivo no tiene formato GGUF.", file=sys.stderr)
            return 1
    h = hashlib.sha256()
    with open(src, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest()
    if args.sha256 and args.sha256.lower() != digest:
        print(f"SHA256 no coincide.\n  esperado {args.sha256}\n  obtenido {digest}", file=sys.stderr)
        return 1
    dst_dir = os.path.join(cfgmod.user_dirs()["data"], "models")
    os.makedirs(dst_dir, mode=0o700, exist_ok=True)
    dst = os.path.join(dst_dir, os.path.basename(src))
    shutil.copy2(src, dst + ".part")
    os.replace(dst + ".part", dst)
    print(f"Instalado {dst}\nSHA256 {digest}")
    return 0


def cmd_nube(args, cfg):
    if args.accion == "estado":
        c = eng.CloudEngine(cfg) if cfg.get("nube_endpoint") else None
        if not c or not c.configured:
            print("Modo nube: desactivado (ATLAS es 100 % local).")
            return 0
        print(f"Modo nube: configurado en {c.base} · modelo {cfg.get('nube_modelo')} · "
              f"pasarela {'disponible' if c.healthy() else 'no responde (¿OmniRoute abierto?)'}")
        print("Solo se usa en las consultas que marques como nube (--nube o el interruptor ☁ del panel).")
        return 0
    if args.accion == "desactivar":
        cfgmod.save_user({"nube_endpoint": ""})
        try:
            os.remove(cfgmod.nube_key_path())
        except OSError:
            pass
        print("Modo nube desactivado y clave borrada. ATLAS vuelve a ser 100 % local.")
        return 0
    if not cfgmod.is_local_endpoint(args.endpoint):
        print("Solo se admite una pasarela LOCAL (p. ej. http://127.0.0.1:20128/v1).", file=sys.stderr)
        return 1
    key = args.clave
    if not key:
        import getpass
        key = getpass.getpass("Clave de OmniRoute (Dashboard → Endpoints): ").strip()
    if not key or any(ch.isspace() for ch in key):
        print("Clave vacía o no válida.", file=sys.stderr)
        return 1
    fd = os.open(cfgmod.nube_key_path(), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(key)
    cfgmod.save_user({"nube_endpoint": args.endpoint, "nube_modelo": args.modelo})
    print("Modo nube configurado. AVISO: en las consultas marcadas como nube, tu texto, archivos y el "
          "texto de tu pantalla salen hacia los proveedores que tengas en OmniRoute.")
    return 0


def cmd_skills(args):
    acc, obj = args.accion, args.objetivo
    try:
        if acc == "lista":
            found, errors = sk.discover()
            for name, s_ in sorted(found.items()):
                tag = " [scripts]" if s_.has_scripts else ""
                print(f"{name:34} {s_.origin:8}{tag}  {s_.description[:90]}")
            print(f"\n{len(found)} skills. Úsalas con: atlas preguntar \"/NOMBRE tu pregunta\" "
                  "(o se activan solas si tu pregunta coincide).")
            for p, e in errors:
                print(f"AVISO {p}: {e}", file=sys.stderr)
            return 0
        if not obj:
            print("Falta el nombre, la ruta o la URL.", file=sys.stderr)
            return 1
        if acc == "info":
            found, _ = sk.discover()
            s_ = found.get(obj)
            if not s_:
                print(f"No existe la skill '{obj}'.", file=sys.stderr)
                return 1
            print(json.dumps(s_.as_dict(), ensure_ascii=False, indent=2))
            return 0
        if acc == "validar":
            s_ = sk.validate(os.path.abspath(obj))
            print(f"Válida: {s_.name}")
            return 0
        if acc == "instalar":
            if obj.startswith("http") and not obj.startswith("https://"):
                print("Solo se aceptan URLs https.", file=sys.stderr)
                return 1
            print("Las skills son INSTRUCCIONES para la IA y pueden traer scripts. Instala solo de fuentes "
                  "en las que confíes; ATLAS nunca ejecuta sus scripts sin tu confirmación.")
            names, problems = sk.install(obj)
            print("Instaladas: " + ", ".join(names))
            for p, e in problems:
                print(f"Omitida {p}: {e}", file=sys.stderr)
            return 0
        if acc == "quitar":
            sk.remove(obj)
            print(f"Quitada: {obj}")
            return 0
        if acc == "exportar":
            dest = os.path.expanduser("~/.claude/skills" if args.claude else "~/.agents/skills")
            print("Copiada a " + sk.export_to(obj, dest))
            return 0
    except (sk.SkillError, OSError) as ex:
        print(f"ATLAS: {ex}", file=sys.stderr)
        return 1
    return 1


def cmd_memoria(args):
    try:
        if args.accion == "indexar":
            if not args.objetivo:
                raise memoria.MemoriaError("indica qué carpetas o archivos indexar (ej. ~/Documentos)")
            st = memoria.index(args.objetivo)
            print(f"Indexado: {st['nuevos']} nuevos, {st['actualizados']} actualizados, "
                  f"{st['sin_cambios']} sin cambios, {st['omitidos']} omitidos ({st['trozos']} trozos).")
        elif args.accion == "actualizar":
            st = memoria.refresh()
            print(f"Actualizado: {st['actualizados']} cambiados, {st['eliminados']} ya no existen.")
        elif args.accion == "buscar":
            hits = memoria.search(" ".join(args.objetivo), k=args.k)
            for h in hits:
                print(f"\n{h['ruta']} (trozo {h['trozo']})\n  " + h["texto"][:300].replace("\n", "\n  "))
            if not hits:
                print("Sin resultados.")
        elif args.accion == "olvidar":
            n = sum(memoria.forget(p) for p in args.objetivo)
            print(f"Olvidados {n} documentos (tus archivos no se tocan).")
        else:
            print(json.dumps(memoria.stats(), ensure_ascii=False, indent=2))
    except memoria.MemoriaError as ex:
        print(f"ATLAS: {ex}", file=sys.stderr)
        return 1
    return 0


def cmd_rutina(args):
    try:
        if args.accion == "lista":
            data = rutinas.load()
            for name, r in sorted(data.items()):
                what = "resumen del día" if r["tipo"] == "resumen" else f"agente: {r['instruccion'][:60]}"
                print(f"{name:20} {r['dias']:13} {r['hora']}  {what}" + ("  🔊" if r.get("voz") else ""))
            if not data:
                print("No hay rutinas. Ejemplo: atlas rutina agregar mi-dia --hora 08:00 --resumen --voz")
            return 0
        if not args.nombre:
            raise rutinas.RutinaError("indica el nombre de la rutina")
        if args.accion == "agregar":
            if bool(args.resumen) == bool(args.agente):
                raise rutinas.RutinaError("elige --resumen o --agente \"instrucción\"")
            r = rutinas.add(args.nombre, args.hora, "resumen" if args.resumen else "agente",
                            args.agente or "", args.dias, args.voz)
            print(f"Rutina '{args.nombre}' programada ({r['dias']} a las {r['hora']}).")
            if not r["temporizador_activo"]:
                print("Aviso: no se pudo activar el temporizador de systemd del usuario; "
                      f"ejecútala a mano con: atlas rutina ejecutar {args.nombre}")
        elif args.accion == "quitar":
            rutinas.remove(args.nombre)
            print(f"Rutina '{args.nombre}' eliminada.")
        elif args.accion == "ultimo":
            print(rutinas.last_result(args.nombre) or "Aún no se ha ejecutado.")
    except rutinas.RutinaError as ex:
        print(f"ATLAS: {ex}", file=sys.stderr)
        return 1
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="atlas",
                                 description="ATLAS — asistente local sin internet")
    sub = ap.add_subparsers(dest="cmd")
    o = sub.add_parser("abrir", help="abrir el panel (por defecto)")
    o.add_argument("--no-navegador", action="store_true")
    s = sub.add_parser("servir", help="servidor del panel (uso interno)")
    s.add_argument("--puerto", type=int)
    p = sub.add_parser("preguntar")
    p.add_argument("--nube", action="store_true", help="usar el modo nube (OmniRoute) en esta consulta")
    p.add_argument("texto", nargs="+")
    ch = sub.add_parser("chat")
    ch.add_argument("--nube", action="store_true")
    pa = sub.add_parser("pantalla")
    pa.add_argument("--nube", action="store_true", help="usar el modo nube (OmniRoute) en esta consulta")
    pa.add_argument("--zona", action="store_true")
    pa.add_argument("--panel", action="store_true",
                    help="capturar YA y mostrar el análisis en el panel (atajo de teclado)")
    pa.add_argument("pregunta", nargs="*")
    e = sub.add_parser("explicar")
    e.add_argument("--nube", action="store_true", help="usar el modo nube (OmniRoute) en esta consulta")
    e.add_argument("archivo")
    e.add_argument("pregunta", nargs="*")
    og = sub.add_parser("organizar")
    og.add_argument("--nube", action="store_true")
    for k in ("nota", "tarea"):
        n = sub.add_parser(k)
        n.add_argument("texto", nargs="+")
        n.add_argument("--fecha")
    sub.add_parser("notas")
    sub.add_parser("tareas")
    hd = sub.add_parser("hecho")
    hd.add_argument("id")
    od = sub.add_parser("orden", help="evaluar y, si procede, ejecutar una orden")
    od.add_argument("orden")
    m = sub.add_parser("modelo")
    m.add_argument("accion", choices=["listar", "instalar"])
    m.add_argument("ruta", nargs="?")
    m.add_argument("--sha256")
    sub.add_parser("estado")
    skp = sub.add_parser("skills", help="Agent Skills (estándar agentskills.io)")
    skp.add_argument("accion", choices=["lista", "info", "instalar", "quitar", "exportar", "validar"])
    skp.add_argument("objetivo", nargs="?", help="nombre de skill, ruta o URL git https")
    skp.add_argument("--claude", action="store_true", help="exportar a ~/.claude/skills (Claude Code)")
    nb = sub.add_parser("nube", help="modo nube opcional vía una pasarela local (OmniRoute)")
    nb.add_argument("accion", choices=["activar", "desactivar", "estado"])
    nb.add_argument("--endpoint", default="http://127.0.0.1:20128/v1")
    nb.add_argument("--modelo", default="auto")
    nb.add_argument("--clave", help="clave de OmniRoute (si no, se pide sin mostrarla)")
    mo = sub.add_parser("motor", help="motor de IA local para otras apps (p. ej. GenOffice)")
    mo.add_argument("accion", choices=["iniciar", "detener", "estado"])
    me = sub.add_parser("memoria", help="índice local de tus documentos (búsqueda con citas)")
    me.add_argument("accion", choices=["indexar", "buscar", "estado", "olvidar", "actualizar"])
    me.add_argument("objetivo", nargs="*", help="rutas a indexar/olvidar o texto a buscar")
    me.add_argument("-k", type=int, default=8)
    iv = sub.add_parser("investigar", help="investigación profunda en tus documentos, con citas")
    iv.add_argument("--nube", action="store_true")
    iv.add_argument("--saltos", type=int)
    iv.add_argument("pregunta", nargs="+")
    ag = sub.add_parser("agente", help="tarea en varios pasos con herramientas (bajo la política de ATLAS)")
    ag.add_argument("--nube", action="store_true")
    ag.add_argument("--pasos", type=int)
    ag.add_argument("tarea", nargs="+")
    rs = sub.add_parser("resumen", help="resumen del día: tareas, notas, actualizaciones")
    rs.add_argument("--nube", action="store_true")
    rs.add_argument("--voz", action="store_true", help="leerlo en voz alta (espeak-ng, local)")
    rs.add_argument("--notificar", action="store_true")
    ru = sub.add_parser("rutina", help="programar el resumen o una tarea del agente")
    ru.add_argument("accion", choices=["agregar", "lista", "quitar", "ejecutar", "ultimo"])
    ru.add_argument("nombre", nargs="?")
    ru.add_argument("--hora", help="HH:MM")
    ru.add_argument("--dias", default="diario", choices=sorted(rutinas.DAYS))
    ru.add_argument("--resumen", action="store_true", help="la rutina es el resumen del día")
    ru.add_argument("--agente", metavar="INSTRUCCION", help="tarea para el agente (solo lectura)")
    ru.add_argument("--voz", action="store_true")
    args = ap.parse_args(argv)
    try:
        cfg = cfgmod.load()
    except ValueError as ex:
        print(ex, file=sys.stderr)
        return 2
    cmd = args.cmd or "abrir"
    if cmd == "abrir":
        if args.cmd is None:
            args.no_navegador = False
        return cmd_open(args, cfg)
    if cmd == "servir":
        web.serve(cfg, port=args.puerto)
        return 0
    if cmd == "modelo":
        return cmd_model(args, cfg)
    if cmd in ("nota", "tarea"):
        it = store.add(cmd + "s", " ".join(args.texto), args.fecha)
        print(f"Guardado ({it['id']}).")
        return 0
    if cmd in ("notas", "tareas"):
        for it in store.list_items(cmd):
            mark = "x" if it["hecho"] else " "
            print(f"[{mark}] {it['id']}  {it['texto']}" + (f"  · {it['fecha']}" if it.get("fecha") else ""))
        return 0
    if cmd == "hecho":
        try:
            store.set_done("tareas", args.id)
        except KeyError:
            print("No existe esa tarea.", file=sys.stderr)
            return 1
        return 0
    if cmd == "orden":
        v = policy.classify(args.orden)
        print(color(v.level, f"[{v.level}] {args.orden}") + f"\n  {v.reason}")
        if not v.runnable:
            return 3
        a = Assistant(eng.Engine(cfg))
        out = a.propose(args.orden)
        print_reply({"respuesta": "", "ordenes": [out]}, a)
        return 0
    if cmd == "skills":
        return cmd_skills(args)
    if cmd == "memoria":
        return cmd_memoria(args)
    if cmd == "rutina" and args.accion != "ejecutar":
        return cmd_rutina(args)
    if cmd == "nube":
        return cmd_nube(args, cfg)
    if cmd == "motor":
        e_ = eng.Engine(cfg)
        if args.accion == "estado":
            print(f"motor {'activo' if e_.healthy(0.5) else 'detenido'} en {cfg['endpoint']}/v1")
            return 0
        if args.accion == "detener":
            print("motor detenido" if eng.stop_detached(cfg["endpoint"]) else "no había un motor iniciado por ATLAS")
            return 0
        try:
            e_.ensure_running()
        except eng.EngineError as ex:
            print(f"ATLAS: {ex}", file=sys.stderr)
            return 1
        print(f"motor activo en {cfg['endpoint']}/v1 (API compatible con OpenAI, solo local)")
        os._exit(0)   # salir sin detener el servidor
    if cmd == "estado":
        e_ = eng.Engine(cfg)
        print(json.dumps({"modelos": eng.find_models(cfg), "vision": e_.vision,
                          "motor_activo": e_.healthy(0.5), "panel": bool(running_web()),
                          "endpoint": cfg["endpoint"]}, ensure_ascii=False, indent=2))
        return 0
    if cmd == "pantalla" and args.panel:
        try:
            path = screen.capture(region=args.zona)
        except screen.ScreenError as ex:
            print(f"ATLAS: {ex}", file=sys.stderr)
            return 1
        args.no_navegador = False
        return cmd_open(args, cfg, "&captura=" + os.path.basename(path))
    a = Assistant(eng.Engine(cfg))
    try:
        if cmd == "preguntar":
            print_reply(a.chat(" ".join(args.texto), nube=args.nube), a)
        elif cmd == "pantalla":
            print_reply(a.look_at_screen(" ".join(args.pregunta), args.zona, nube=args.nube), a)
        elif cmd == "explicar":
            print_reply(a.explain_file(args.archivo, " ".join(args.pregunta), nube=args.nube), a)
        elif cmd == "organizar":
            print_reply(a.organize(nube=args.nube), a)
        elif cmd == "investigar":
            print_reply(a.research(" ".join(args.pregunta), nube=args.nube, hops=args.saltos), a)
        elif cmd == "agente":
            print_reply(a.agent(" ".join(args.tarea), nube=args.nube, max_steps=args.pasos), a)
        elif cmd == "resumen":
            out = a.digest(nube=args.nube)
            print_reply(out, a, interactive=False)
            if args.notificar:
                rutinas.notify("ATLAS · Resumen del día", out["respuesta"])
            if args.voz:
                rutinas.speak(out["respuesta"])
        elif cmd == "rutina":
            if not args.nombre:
                raise ValueError("indica el nombre de la rutina")
            print(rutinas.execute(args.nombre, a)["respuesta"])
        elif cmd == "chat":
            print("ATLAS · escribe 'salir' para terminar")
            while True:
                try:
                    t = input("› ").strip()
                except EOFError:
                    break
                if t in ("salir", "exit", "quit"):
                    break
                if t:
                    print_reply(a.chat(t, nube=args.nube), a)
    except (eng.EngineError, screen.ScreenError, FileNotFoundError, ValueError, PermissionError,
            memoria.MemoriaError, rutinas.RutinaError) as ex:
        print(f"ATLAS: {ex}", file=sys.stderr)
        return 1
    finally:
        a.engine.stop()
    return 0
