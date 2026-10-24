"""Notas y tareas locales (JSON en ~/.local/share/novora-atlas, 0600)."""
import json
import os
import threading
import time
import uuid

from . import config as cfgmod

_lock = threading.Lock()


def _path(kind):
    return os.path.join(cfgmod.user_dirs()["data"], f"{kind}.json")


def _load(kind):
    try:
        with open(_path(kind), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save(kind, items):
    p = _path(kind)
    tmp = p + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def add(kind, text, due=None):
    text = (text or "").strip()
    if not text:
        raise ValueError("texto vacío")
    item = {"id": uuid.uuid4().hex[:8], "texto": text[:4000],
            "creado": time.strftime("%Y-%m-%d %H:%M"), "hecho": False}
    if due:
        item["fecha"] = str(due)[:32]
    with _lock:
        items = _load(kind)
        items.append(item)
        _save(kind, items)
    return item


def list_items(kind):
    return _load(kind)


def set_done(kind, item_id, done=True):
    with _lock:
        items = _load(kind)
        for it in items:
            if it["id"] == item_id:
                it["hecho"] = bool(done)
                _save(kind, items)
                return it
    raise KeyError(item_id)


def remove(kind, item_id):
    with _lock:
        items = _load(kind)
        new = [it for it in items if it["id"] != item_id]
        if len(new) == len(items):
            raise KeyError(item_id)
        _save(kind, new)
