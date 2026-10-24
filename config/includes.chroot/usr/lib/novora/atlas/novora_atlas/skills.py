"""Agent Skills (estándar abierto, https://agentskills.io) para ATLAS.

Divulgación progresiva, adaptada a un modelo local pequeño:
  1. Catálogo: nombre + descripción de cada skill (se descubre al iniciar).
  2. Instrucciones: el cuerpo de SKILL.md, SOLO al activar una skill, recortado
     al presupuesto de contexto del modelo local.
  3. Recursos: scripts/ references/ assets/ se leen bajo demanda; los scripts
     NUNCA se ejecutan solos: pasan por la política de órdenes y tu confirmación.

Activación: explícita (`/nombre-skill pregunta`) o automática por coincidencia
léxica entre la pregunta y nombre/descripción (los modelos de 3-4B no usan
herramientas de forma fiable, así que ATLAS decide, no el modelo).

Ubicaciones (de menor a mayor prioridad; la última gana si hay nombres repetidos):
  /usr/share/novora-atlas/skills      incluidas en NOVORA OS (revisadas, Apache-2.0)
  ~/.agents/skills                    convención compartida entre clientes
  ~/.local/share/novora-atlas/skills  instaladas con `atlas skills instalar`
No se cargan skills de proyectos (carpetas .agents/ de repositorios clonados),
porque pueden venir de fuentes no confiables.
"""
import os
import re
import shutil
import subprocess
import tempfile

from . import config as cfgmod

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
STOP = set("""a al algo como con de del el ella en es esta este esto la las lo los me mi mis
para por que se si sin su sus te tu un una uno y o the a an and or of to in for on with
is are be use when this that it its your you how what can""".split())


class SkillError(Exception):
    pass


def system_dirs():
    return [os.environ.get("NOVORA_ATLAS_SKILLS_SYSTEM", "/usr/share/novora-atlas/skills")]


def user_dirs():
    home = os.path.expanduser("~")
    return [os.path.join(home, ".agents", "skills"),
            os.path.join(cfgmod.user_dirs()["data"], "skills")]


# --- YAML mínimo (sin dependencias) para el frontmatter de SKILL.md -------------
def _unquote(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def parse_frontmatter(text):
    """Devuelve (campos, cuerpo). Soporta `clave: valor`, valores entre comillas,
    bloques `>` / `|` y un mapa anidado de un nivel (metadata)."""
    if not text.startswith("---"):
        raise SkillError("SKILL.md sin frontmatter YAML")
    end = text.find("\n---", 3)
    if end < 0:
        raise SkillError("frontmatter sin cierre '---'")
    block, body = text[3:end].strip("\n"), text[end + 4:].lstrip("\n")
    fields, lines, i = {}, block.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not m:
            raise SkillError(f"línea de frontmatter no válida: {line[:60]}")
        key, val = m.group(1), m.group(2)
        i += 1
        if val in (">", "|", ">-", "|-", ""):
            sub = []
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                sub.append(lines[i])
                i += 1
            if val == "" and sub and all(re.match(r"^\s+[A-Za-z0-9_.-]+:\s*", s) or not s.strip() for s in sub):
                fields[key] = {k.strip(): _unquote(v) for k, v in
                               (s.split(":", 1) for s in sub if s.strip())}
            else:
                joiner = "\n" if val.startswith("|") else " "
                fields[key] = joiner.join(s.strip() for s in sub).strip()
        else:
            fields[key] = _unquote(val)
    return fields, body


class Skill:
    def __init__(self, path, fields, body, origin):
        self.path, self.fields, self.body, self.origin = path, fields, body, origin
        self.name = fields["name"]
        self.description = fields["description"]

    @property
    def has_scripts(self):
        return os.path.isdir(os.path.join(self.path, "scripts"))

    def as_dict(self):
        return {"nombre": self.name, "descripcion": self.description, "origen": self.origin,
                "ruta": self.path, "licencia": self.fields.get("license", "(no indicada)"),
                "scripts": self.has_scripts}


def validate(path):
    """Valida una skill según la especificación. Devuelve Skill o lanza SkillError."""
    md = os.path.join(path, "SKILL.md")
    if not os.path.isfile(md) or os.path.islink(md):
        raise SkillError("falta SKILL.md")
    with open(md, encoding="utf-8", errors="replace") as fh:
        fields, body = parse_frontmatter(fh.read())
    name = str(fields.get("name", ""))
    desc = str(fields.get("description", ""))
    if not (1 <= len(name) <= 64 and NAME_RE.match(name)):
        raise SkillError(f"nombre no válido '{name}' (minúsculas, números y guiones; máx. 64)")
    if name != os.path.basename(os.path.normpath(path)):
        raise SkillError(f"el nombre '{name}' no coincide con la carpeta")
    if not desc.strip():
        raise SkillError("descripción vacía")
    if len(desc) > 1024:      # fuera de la especificación: se carga recortada (guía de clientes)
        fields["description"] = desc[:1021] + "..."
    comp = fields.get("compatibility")
    if comp is not None and not (1 <= len(str(comp)) <= 500):
        raise SkillError("compatibility debe tener entre 1 y 500 caracteres")
    return Skill(path, fields, body, "")


SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv"}


def _skill_dirs(base, max_depth=4):
    """Carpetas con SKILL.md hasta max_depth niveles (colecciones incluidas)."""
    out = []
    base_depth = base.rstrip(os.sep).count(os.sep)
    for dp, dirs, files in os.walk(base, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        if dp.count(os.sep) - base_depth >= max_depth:
            dirs[:] = []
        if "SKILL.md" in files and dp != base:
            out.append(dp)
            dirs[:] = []          # una skill no contiene otras skills
    return out


def discover():
    found, errors = {}, []
    for origin, dirs in (("sistema", system_dirs()), ("usuario", user_dirs())):
        for base in dirs:
            if not os.path.isdir(base):
                continue
            for p in _skill_dirs(base):
                try:
                    s = validate(p)
                except (SkillError, OSError) as ex:
                    errors.append((p, str(ex)))
                    continue
                s.origin = origin
                found[s.name] = s          # la ubicación de usuario reemplaza a la del sistema
    return found, errors


ES_EN = {
    "probar": "test testing", "prueba": "test testing", "pruebas": "tests testing", "testear": "test testing",
    "depurar": "debug debugging", "depuración": "debugging", "error": "error bug", "errores": "errors bugs",
    "fallo": "bug failure", "falla": "bug failure", "rendimiento": "performance", "lento": "performance slow",
    "optimizar": "optimize optimization performance", "seguridad": "security hardening",
    "vulnerabilidad": "security vulnerability", "revisar": "review", "revisión": "review",
    "código": "code", "calidad": "quality", "simplificar": "simplify simplification",
    "documentar": "documentation document", "documentación": "documentation", "diseño": "design",
    "interfaz": "interface frontend", "aplicación": "app application", "web": "web",
    "servidor": "server", "plan": "planning plan", "planificar": "planning plan", "tareas": "tasks",
    "dividir": "breakdown", "especificación": "spec specification", "requisitos": "spec requirements",
    "idea": "idea", "ideas": "ideas", "lanzar": "launch shipping", "publicar": "shipping release launch",
    "versión": "versioning version", "versiones": "versioning", "rama": "git branch", "commit": "git commit",
    "integración": "ci integration", "despliegue": "deployment cd", "automatizar": "automation",
    "registro": "logging observability", "métricas": "metrics observability", "monitoreo": "observability monitoring",
    "migrar": "migration", "migración": "migration", "obsoleto": "deprecation", "navegador": "browser",
    "tema": "theme", "colores": "colors theme", "diapositivas": "slides", "presentación": "presentation slides",
    "arte": "art", "imagen": "image", "imágenes": "images", "gif": "gif", "marca": "brand",
    "comunicado": "communications comms", "boletín": "newsletter comms", "habilidad": "skill",
    "habilidades": "skills", "crear": "create", "construir": "build", "contexto": "context",
}


def _words(text):
    raw = {w for w in re.findall(r"[a-záéíóúñü0-9]+", text.lower()) if len(w) > 2 and w not in STOP}
    out = set(raw)
    for w in raw:
        out.update(ES_EN.get(w, "").split())
    return out


def match(skills, question, threshold=2):
    """Skill más relevante por coincidencia léxica (o None)."""
    q = _words(question)
    best, best_score = None, 0
    for s in skills.values():
        name_words = set(s.name.split("-"))
        score = 2 * len(q & name_words) + len(q & _words(s.description))
        if score > best_score:
            best, best_score = s, score
    return best if best_score >= threshold else None


def activation_text(skill, max_chars):
    body = skill.body
    cut = ""
    if len(body) > max_chars:
        body = body[:max_chars]
        cut = ("\n\n[Instrucciones recortadas por el tamaño del contexto local; "
               f"el texto completo está en {skill.path}/SKILL.md]")
    extra = ""
    if skill.has_scripts:
        extra = (f"\nLos scripts de esta skill están en {skill.path}/scripts/. Si hace falta uno, "
                 "propónlo con 'ORDEN:' usando su ruta absoluta; el usuario decide si se ejecuta.")
    return (f"Skill activa: {skill.name} (carpeta {skill.path}). Sigue estas instrucciones para "
            f"esta tarea; las rutas relativas son respecto a esa carpeta.{extra}\n\n"
            f"<skill nombre=\"{skill.name}\">\n{body}{cut}\n</skill>")


def install(source):
    """Instala una skill (o una carpeta con varias) desde una ruta local o un
    repositorio git https. Valida todo antes de copiar; no ejecuta nada."""
    dest_base = user_dirs()[1]
    os.makedirs(dest_base, exist_ok=True)
    tmp = None
    if re.match(r"^https://[A-Za-z0-9.-]+/[\w./-]+$", source):
        tmp = tempfile.mkdtemp(prefix="skill-")
        r = subprocess.run(["git", "clone", "--depth", "1", "--quiet", source, tmp],
                           capture_output=True, text=True)
        if r.returncode != 0:
            shutil.rmtree(tmp, ignore_errors=True)
            raise SkillError(f"git clone falló: {r.stderr.strip()[:200]}")
        root = tmp
    else:
        root = os.path.abspath(os.path.expanduser(source))
        if not os.path.isdir(root):
            raise SkillError(f"no existe la carpeta {root}")
    try:
        if os.path.isfile(os.path.join(root, "SKILL.md")):          # una sola skill
            s = validate(root)
            target = os.path.join(dest_base, s.name)
            if os.path.exists(target):
                shutil.rmtree(target)
            shutil.copytree(root, target, symlinks=False, ignore=shutil.ignore_patterns(*SKIP_DIRS))
            return [s.name], []
        # Colección: se copia entera (las skills pueden enlazar ../../references).
        installed, problems = [], []
        for c in _skill_dirs(root):
            try:
                installed.append(validate(c).name)
            except SkillError as ex:
                problems.append((os.path.relpath(c, root), str(ex)))
        if not installed:
            raise SkillError("no se encontró ninguna skill válida" +
                             (f": {problems[0][1]}" if problems else ""))
        label = re.sub(r"[^a-z0-9-]+", "-", os.path.basename(source.rstrip("/")).lower().removesuffix(".git"))
        target = os.path.join(dest_base, label.strip("-") or "coleccion")
        if os.path.exists(target):
            shutil.rmtree(target)
        shutil.copytree(root, target, symlinks=False, ignore=shutil.ignore_patterns(*SKIP_DIRS))
        return installed, problems
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def remove(name):
    """Quita una skill o una colección instalada por el usuario con ATLAS."""
    if not NAME_RE.match(name or ""):
        raise SkillError("nombre no válido")
    base = user_dirs()[1]
    target = os.path.join(base, name)
    if not os.path.isdir(target):
        raise SkillError("solo se pueden quitar skills/colecciones instaladas con `atlas skills instalar`")
    shutil.rmtree(target)


def export_to(name, client_dir):
    """Copia una skill a la carpeta de otro cliente (p. ej. ~/.claude/skills)."""
    skills, _ = discover()
    s = skills.get(name)
    if not s:
        raise SkillError(f"no existe la skill '{name}'")
    os.makedirs(client_dir, exist_ok=True)
    target = os.path.join(client_dir, s.name)
    if os.path.exists(target):
        shutil.rmtree(target)
    shutil.copytree(s.path, target, symlinks=False)
    return target
