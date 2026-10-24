"""Memoria de ATLAS: índice local de documentos con búsqueda de texto completo.

  * SQLite + FTS5 (incluidos en Python): sin servicios ni dependencias.
  * Base en ~/.local/share/novora-atlas/memoria.db (permisos 0600).
  * Solo se lee: ATLAS nunca modifica los archivos que indexa.
  * Se omiten carpetas y archivos ocultos (.ssh, .gnupg, .config…), enlaces
    simbólicos y rutas de sistema (/dev, /proc, /sys, /run, /boot).
"""
import os
import re
import sqlite3
import subprocess
import threading
import time

from . import config as cfgmod

TEXT_EXT = {
    ".txt", ".md", ".markdown", ".rst", ".org", ".tex", ".csv", ".tsv", ".json", ".jsonl",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".xml", ".html", ".htm", ".log",
    ".py", ".pyw", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".java", ".kt", ".kts", ".gradle",
    ".cs", ".csproj", ".sln", ".xaml", ".props", ".targets", ".c", ".h", ".cpp", ".hpp", ".cc",
    ".rs", ".go", ".rb", ".php", ".lua", ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat",
    ".sql", ".swift", ".dart", ".vue", ".svelte", ".css", ".scss", ".r", ".m", ".pl",
}
OFFICE_EXT = {".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt"}
PDF_EXT = {".pdf"}
SKIP_DIRS = {"node_modules", "bin", "obj", "build", "dist", "target", "__pycache__",
             "venv", "site-packages", "Pods", "DerivedData"}
SYSTEM_ROOTS = ("/dev", "/proc", "/sys", "/run", "/boot")
CHUNK, OVERLAP = 1200, 200
MAX_FILES = 20000
MAX_BYTES = 5 * 1024 * 1024

_lock = threading.Lock()


class MemoriaError(Exception):
    pass


def db_path():
    return os.path.join(cfgmod.user_dirs()["data"], "memoria.db")


def _connect():
    p = db_path()
    os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)
    if not os.path.exists(p):
        os.close(os.open(p, os.O_WRONLY | os.O_CREAT, 0o600))
    con = sqlite3.connect(p, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS docs(ruta TEXT PRIMARY KEY, mtime REAL, tamano INTEGER,
                                        indexado TEXT, trozos INTEGER);
        CREATE VIRTUAL TABLE IF NOT EXISTS trozos USING fts5(
            ruta UNINDEXED, n UNINDEXED, texto, tokenize='unicode61 remove_diacritics 2');
    """)
    return con


def _is_system(path):
    return any(path == r or path.startswith(r + "/") for r in SYSTEM_ROOTS)


def _hidden(name):
    return name.startswith(".")


def chunk_text(text, size=CHUNK, overlap=OVERLAP):
    """Trozos de ~size caracteres, cortados en saltos de línea cuando se puede."""
    text = text.replace("\r\n", "\n")
    out, i, n = [], 0, len(text)
    while i < n:
        end = min(n, i + size)
        if end < n:
            cut = text.rfind("\n", i + size // 2, end)
            if cut > i:
                end = cut
        piece = text[i:end].strip()
        if piece:
            out.append(piece)
        if end >= n:
            break
        i = max(end - overlap, i + 1)
    return out


def extract(path):
    """Texto de un archivo, o None si no es un tipo admitido."""
    ext = os.path.splitext(path)[1].lower()
    if ext in TEXT_EXT:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_BYTES)
        if b"\0" in raw[:4096]:
            return None
        return raw.decode("utf-8", errors="replace")
    if ext in OFFICE_EXT:
        from .assistant import office_to_text
        try:
            return office_to_text(path)
        except ValueError:
            return None
    if ext in PDF_EXT:
        exe = os.environ.get("NOVORA_ATLAS_PDFTOTEXT", "pdftotext")
        try:
            r = subprocess.run([exe, "-layout", "-enc", "UTF-8", path, "-"], capture_output=True,
                               text=True, timeout=60, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return r.stdout if r.returncode == 0 else None
    return None


def _walk(root):
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not _hidden(d) and d not in SKIP_DIRS)
        for f in sorted(filenames):
            if not _hidden(f):
                yield os.path.join(dirpath, f)


def index(paths, progress=None):
    """Indexa archivos o carpetas. Devuelve un resumen."""
    stats = {"nuevos": 0, "actualizados": 0, "sin_cambios": 0, "omitidos": 0, "trozos": 0}
    with _lock:
        con = _connect()
        try:
            count = 0
            for raw in paths:
                root = os.path.realpath(os.path.expanduser(raw))
                if not os.path.exists(root):
                    raise MemoriaError(f"no existe: {raw}")
                if _is_system(root):
                    raise MemoriaError(f"ATLAS no indexa rutas de sistema ({root})")
                for path in _walk(root):
                    count += 1
                    if count > MAX_FILES:
                        raise MemoriaError(f"demasiados archivos (máximo {MAX_FILES}); elige una carpeta más concreta")
                    try:
                        st = os.lstat(path)
                    except OSError:
                        stats["omitidos"] += 1
                        continue
                    if not os.path.isfile(path) or os.path.islink(path) or st.st_size > MAX_BYTES * 4:
                        stats["omitidos"] += 1
                        continue
                    row = con.execute("SELECT mtime, tamano FROM docs WHERE ruta=?", (path,)).fetchone()
                    if row and row[0] == st.st_mtime and row[1] == st.st_size:
                        stats["sin_cambios"] += 1
                        continue
                    try:
                        text = extract(path)
                    except OSError:
                        text = None
                    if not text or not text.strip():
                        stats["omitidos"] += 1
                        continue
                    pieces = chunk_text(text)
                    con.execute("DELETE FROM trozos WHERE ruta=?", (path,))
                    con.executemany("INSERT INTO trozos(ruta, n, texto) VALUES (?,?,?)",
                                    [(path, i, t) for i, t in enumerate(pieces)])
                    con.execute("INSERT OR REPLACE INTO docs VALUES (?,?,?,?,?)",
                                (path, st.st_mtime, st.st_size, time.strftime("%Y-%m-%d %H:%M"), len(pieces)))
                    stats["actualizados" if row else "nuevos"] += 1
                    stats["trozos"] += len(pieces)
                    if progress:
                        progress(path)
            con.commit()
        finally:
            con.close()
    return stats


WORD = re.compile(r"[\w][\w.\-]*", re.U)
STOP = {"el", "la", "los", "las", "de", "del", "y", "o", "a", "en", "un", "una", "que", "es",
        "por", "para", "con", "se", "su", "lo", "al", "como", "me", "mi", "qué", "cómo", "cuál",
        "the", "of", "and", "or", "to", "in", "is", "a", "an", "for", "on", "with", "what", "how"}


def fts_query(text):
    """Convierte texto libre en una consulta FTS5 segura (sin sintaxis del usuario)."""
    words = [w.lower().strip(".-") for w in WORD.findall(text or "")]
    words = [w for w in words if w and w not in STOP][:24]
    return " OR ".join('"' + w.replace('"', "") + '"' for w in dict.fromkeys(words))


def search(query, k=8):
    q = fts_query(query)
    if not q:
        return []
    with _lock:
        con = _connect()
        try:
            rows = con.execute(
                "SELECT ruta, n, texto, bm25(trozos) AS r FROM trozos WHERE trozos MATCH ? "
                "ORDER BY r LIMIT ?", (q, max(1, min(int(k), 50)))).fetchall()
        except sqlite3.OperationalError as ex:
            raise MemoriaError(f"consulta no válida: {ex}") from ex
        finally:
            con.close()
    return [{"ruta": r[0], "trozo": r[1], "texto": r[2], "puntuacion": round(-r[3], 3)} for r in rows]


def stats():
    with _lock:
        con = _connect()
        try:
            docs, trozos = con.execute("SELECT COUNT(*), COALESCE(SUM(trozos),0) FROM docs").fetchone()
            ult = con.execute("SELECT MAX(indexado) FROM docs").fetchone()[0]
        finally:
            con.close()
    return {"documentos": docs, "trozos": trozos, "ultima_indexacion": ult, "base": db_path()}


def forget(path):
    """Quita del índice un archivo o todo lo que hay bajo una carpeta."""
    root = os.path.realpath(os.path.expanduser(path))
    with _lock:
        con = _connect()
        try:
            like = root.rstrip("/") + "/%"
            n = con.execute("SELECT COUNT(*) FROM docs WHERE ruta=? OR ruta LIKE ?", (root, like)).fetchone()[0]
            con.execute("DELETE FROM trozos WHERE ruta=? OR ruta LIKE ?", (root, like))
            con.execute("DELETE FROM docs WHERE ruta=? OR ruta LIKE ?", (root, like))
            con.commit()
        finally:
            con.close()
    return n


def refresh():
    """Vuelve a indexar lo ya indexado (cambios) y olvida lo que ya no existe."""
    with _lock:
        con = _connect()
        try:
            paths = [r[0] for r in con.execute("SELECT ruta FROM docs")]
        finally:
            con.close()
    gone = [p for p in paths if not os.path.isfile(p)]
    for p in gone:
        forget(p)
    live = [p for p in paths if os.path.isfile(p)]
    st = index(live) if live else {"nuevos": 0, "actualizados": 0, "sin_cambios": 0, "omitidos": 0, "trozos": 0}
    st["eliminados"] = len(gone)
    return st
