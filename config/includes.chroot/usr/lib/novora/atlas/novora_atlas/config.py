"""Configuración de ATLAS.

Orden de carga: valores por defecto -> /etc/novora-atlas/config.json ->
~/.config/novora-atlas/config.json -> variables NOVORA_ATLAS_*.
"""
import json
import os

DEFAULTS = {
    # Motor local (API compatible con OpenAI). Solo se aceptan direcciones
    # locales: ATLAS no usa internet.
    "endpoint": "http://127.0.0.1:8181",
    "manage_server": True,          # ATLAS arranca/para llama-server
    "server_binary": "llama-server",
    "models_dirs": ["/usr/share/novora-atlas/models",
                    "~/.local/share/novora-atlas/models"],
    "chat_model": "",               # nombre de archivo .gguf; "" = el primero
    "vision_mmproj": "",            # proyector multimodal .gguf (opcional)
    "context": 8192,                # el modo agente e investigar necesitan más contexto
    "gpu_layers": 99,               # llama.cpp ignora si no hay backend GPU
    "server_idle_seconds": 600,     # liberar RAM/VRAM tras 10 min sin uso
    "web_port": 8190,
    "web_idle_seconds": 1800,
    "language": "es",
    "ocr_langs": "spa+eng",
    "command_timeout": 60,
    "max_file_bytes": 200000,
    "skills_auto": True,            # activar skills por coincidencia con la pregunta
    "skill_max_chars": 6000,        # presupuesto de instrucciones por skill (contexto local)
    # Modo nube OPCIONAL a través de una pasarela LOCAL (OmniRoute, 127.0.0.1:20128).
    # Vacío = desactivado. Solo se usa en las consultas que marques como "nube".
    "nube_endpoint": "",
    "nube_modelo": "auto",
    "nube_skill_max_chars": 40000,
    # Agente, investigación y rutinas (funciones al estilo OpenJarvis, dentro de ATLAS)
    "agente_max_pasos": 8,
    "agente_auto_lectura": True,    # el agente ejecuta solo órdenes de SOLO LECTURA sin preguntar
    "investigar_saltos": 4,
}
SYSTEM_FILE = "/etc/novora-atlas/config.json"


def _expand(path):
    return os.path.abspath(os.path.expanduser(path))


def user_dirs():
    home = os.path.expanduser("~")

    def xdg(var, default):
        # Según XDG, una variable vacía o relativa se ignora.
        val = os.environ.get(var) or ""
        return val if os.path.isabs(val) else os.path.join(home, default)
    return {
        "config": os.path.join(xdg("XDG_CONFIG_HOME", ".config"), "novora-atlas"),
        "data": os.path.join(xdg("XDG_DATA_HOME", ".local/share"), "novora-atlas"),
        "state": os.path.join(xdg("XDG_STATE_HOME", ".local/state"), "novora-atlas"),
    }


def is_local_endpoint(url):
    from urllib.parse import urlparse
    u = urlparse(url)
    return u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost", "::1")


def nube_key_path():
    return os.path.join(user_dirs()["config"], "nube.key")


def save_user(changes):
    """Guarda claves en ~/.config/novora-atlas/config.json (0600)."""
    path = os.path.join(user_dirs()["config"], "config.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    data.update(changes)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    os.replace(path + ".tmp", path)


def load():
    cfg = dict(DEFAULTS)
    for path in (os.environ.get("NOVORA_ATLAS_SYSTEM_CONFIG", SYSTEM_FILE),
                 os.path.join(user_dirs()["config"], "config.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass
    for key in DEFAULTS:
        env = os.environ.get("NOVORA_ATLAS_" + key.upper())
        if env is None:
            continue
        default = DEFAULTS[key]
        if isinstance(default, bool):
            cfg[key] = env in ("1", "true", "yes")
        elif isinstance(default, int):
            cfg[key] = int(env)
        elif isinstance(default, list):
            cfg[key] = env.split(":")
        else:
            cfg[key] = env
    if not is_local_endpoint(cfg["endpoint"]):
        raise ValueError("ATLAS solo admite motores locales "
                         "(http://127.0.0.1 o localhost)")
    if cfg["nube_endpoint"] and not is_local_endpoint(cfg["nube_endpoint"]):
        raise ValueError("el modo nube solo admite una pasarela local (p. ej. OmniRoute en "
                         "http://127.0.0.1:20128/v1); ATLAS nunca habla directo con internet")
    cfg["models_dirs"] = [_expand(p) for p in cfg["models_dirs"]]
    for d in user_dirs().values():
        os.makedirs(d, mode=0o700, exist_ok=True)
    return cfg
