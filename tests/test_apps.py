"""Pruebas de novora-apps con un GitHub simulado (servidor HTTP local) y
programas falsos para pkexec/npm/node. No instala nada en el sistema."""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
APPS = os.path.join(HERE, "..", "config/includes.chroot/usr/local/bin/novora-apps")
TMP = tempfile.mkdtemp(prefix="novora-apps-")
FILES, RELEASES = {}, {}


_DEBS = {}


def make_deb(pkg):
    if pkg in _DEBS:
        return _DEBS[pkg]
    root = os.path.join(TMP, "debsrc-" + pkg)
    os.makedirs(os.path.join(root, "DEBIAN"), exist_ok=True)
    with open(os.path.join(root, "DEBIAN/control"), "w") as fh:
        fh.write(f"Package: {pkg}\nVersion: 1.0\nArchitecture: amd64\nMaintainer: t <t@t>\nDescription: t\n")
    out = os.path.join(TMP, f"{pkg}_1.0_amd64.deb")
    subprocess.run(["dpkg-deb", "--build", "--root-owner-group", root, out], check=True, capture_output=True)
    with open(out, "rb") as fh:
        _DEBS[pkg] = fh.read()
    return _DEBS[pkg]


def make_tar(members):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data in members:
            ti = tarfile.TarInfo(name)
            ti.size, ti.mode = len(data), 0o755
            tf.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def publish(repo, tag, assets, digest="ok"):
    out = []
    for name, data in assets:
        FILES[f"/dl/{repo}/{name}"] = data
        d = {"name": name, "browser_download_url": f"{BASE}/dl/{repo}/{name}"}
        if digest == "ok":
            d["digest"] = "sha256:" + hashlib.sha256(data).hexdigest()
        elif digest == "bad":
            d["digest"] = "sha256:" + "0" * 64
        out.append(d)
    RELEASES[f"/repos/{repo}/releases/latest"] = {"tag_name": tag, "assets": out}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path in RELEASES:
            body = json.dumps(RELEASES[self.path]).encode()
        elif self.path in FILES:
            body = FILES[self.path]
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


SRV = ThreadingHTTPServer(("127.0.0.1", 0), H)
BASE = f"http://127.0.0.1:{SRV.server_port}"
threading.Thread(target=SRV.serve_forever, daemon=True).start()
BIN = os.path.join(TMP, "bin")
os.makedirs(BIN)
LOG = os.path.join(TMP, "calls.log")
for name, body in {"pkexec": 'echo "pkexec $*" >> "$LOG"',
                   "npm": 'echo "npm $*" >> "$LOG"',
                   "node16": "echo v16.20.0", "node20": "echo v20.19.2"}.items():
    with open(os.path.join(BIN, name), "w") as fh:
        fh.write(f"#!/bin/sh\n{body}\n")
    os.chmod(os.path.join(BIN, name), 0o755)


class Apps(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(dir=TMP)
        open(LOG, "w").close()

    def run_apps(self, *args, inp="", node="node20"):
        env = {"PATH": os.environ["PATH"], "HOME": self.home, "LOG": LOG, "NOVORA_APPS_API": BASE,
               "NOVORA_APPS_PKEXEC": os.path.join(BIN, "pkexec"), "NOVORA_APPS_NPM": os.path.join(BIN, "npm"),
               "NOVORA_APPS_NODE": os.path.join(BIN, node)}
        return subprocess.run([sys.executable, "-I", APPS, *args], input=inp, env=env,
                              capture_output=True, text=True, timeout=60)

    @staticmethod
    def jload(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def calls(self):
        with open(LOG) as fh:
            return fh.read()

    def test_list(self):
        r = self.run_apps("lista")
        for n in ("genoffice", "spotifast", "zuno", "huntly", "claude-code", "codex", "gemini-cli", "copilot-cli"):
            self.assertIn(n, r.stdout)
        self.assertIn("[nube]", r.stdout)

    def test_genoffice_verified_install_without_analytics_and_local_ai(self):
        publish("genspark-ai/genoffice", "v1.2.0", [("genoffice_1.2.0_amd64.deb", make_deb("genoffice"))])
        r = self.run_apps("instalar", "genoffice", inp="si\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Verificado genoffice_1.2.0_amd64.deb", r.stdout)
        self.assertRegex(self.calls(), r"pkexec apt-get install -y /.*/genoffice_1\.2\.0_amd64\.deb")
        cfg = os.path.join(self.home, ".config/GenOffice")
        self.assertIs(self.jload(os.path.join(cfg, "app-settings.json"))["analyticsEnabled"], False)
        ai = self.jload(os.path.join(cfg, "ai-settings.json"))
        self.assertEqual((ai["provider"], ai["providers"]["custom"]["baseUrl"], ai["gskToolsEnabled"]),
                         ("custom", "http://127.0.0.1:8181/v1", False))
        r = self.run_apps("quitar", "genoffice")
        self.assertIn("pkexec apt-get remove -y genoffice", self.calls())

    def test_existing_genoffice_ai_settings_are_kept(self):
        publish("genspark-ai/genoffice", "v1.2.0", [("genoffice_1.2.0_amd64.deb", make_deb("genoffice"))])
        cfg = os.path.join(self.home, ".config/GenOffice")
        os.makedirs(cfg)
        for fname, data in (("ai-settings.json", {"provider": "anthropic"}),
                            ("app-settings.json", {"analyticsEnabled": True, "otro": 1})):
            with open(os.path.join(cfg, fname), "w", encoding="utf-8") as fh:
                json.dump(data, fh)
        self.run_apps("instalar", "genoffice", inp="si\n")
        self.assertEqual(self.jload(os.path.join(cfg, "ai-settings.json"))["provider"], "anthropic")
        st = self.jload(os.path.join(cfg, "app-settings.json"))
        self.assertEqual((st["analyticsEnabled"], st["otro"]), (False, 1))

    def test_wrong_digest_is_rejected_and_nothing_installed(self):
        publish("crmne/spotifast", "v2", [("spotifast_2_amd64.deb", make_deb("spotifast"))], digest="bad")
        r = self.run_apps("instalar", "spotifast", inp="si\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("NO coincide", r.stderr)
        self.assertEqual(self.calls(), "")

    def test_missing_digest_requires_explicit_flag(self):
        publish("lcomplete/huntly", "v0.5", [("huntly_0.5_amd64.deb", make_deb("huntly"))], digest=None)
        r = self.run_apps("instalar", "huntly", inp="si\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no publica la huella", r.stderr)
        r = self.run_apps("instalar", "huntly", "--sin-verificar", inp="si\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("SIN verificar", r.stdout)

    def test_zuno_requires_explicit_tos_acceptance(self):
        publish("noFAYZ/zuno", "v1.3.2", [("zuno_1.3.2_amd64.deb", make_deb("zuno"))])
        r = self.run_apps("instalar", "zuno", inp="si\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Términos de Servicio de YouTube", r.stdout)
        self.assertEqual(self.calls(), "")
        r = self.run_apps("instalar", "zuno", inp="ACEPTO\n")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_cloud_ai_warns_and_checks_node(self):
        r = self.run_apps("instalar", "gemini-cli", inp="si\n", node="node16")
        self.assertIn("envía tus preguntas, código y archivos a Google", r.stdout)
        self.assertEqual(r.returncode, 1)
        self.assertIn("Node.js 20", r.stderr)
        r = self.run_apps("instalar", "claude-code", inp="si\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"npm install -g --prefix {self.home}/.local @anthropic-ai/claude-code", self.calls())
        r = self.run_apps("instalar", "codex", inp="no\n")
        self.assertIn("Cancelado", r.stdout)

    def test_omniroute_installs_bound_to_localhost(self):
        publish("cheaper-inference/OmniRoute", "v3.8.53", [("omniroute_3.8.53_amd64.deb", make_deb("omniroute")),
                                                           ("omniroute_3.8.53_arm64.deb", b"no")])
        r = self.run_apps("instalar", "omniroute", inp="si\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("MITM/TPROXY", r.stdout)
        self.assertRegex(self.calls(), r"apt-get install -y /.*omniroute_3\.8\.53_amd64\.deb")
        with open(os.path.join(self.home, ".config/environment.d/90-novora-omniroute.conf")) as fh:
            conf = fh.read()
        for k in ("API_HOST=127.0.0.1", "OMNIROUTE_SERVER_HOST=127.0.0.1", "HOST=127.0.0.1"):
            self.assertIn(k, conf)

    def test_copilot_tarball_installs_symlink(self):
        publish("github/copilot-cli", "v1.0.68",
                [("copilot-linux-x64.tar.gz", make_tar([("copilot-linux-x64/copilot", b"#!/bin/sh\necho hola\n")]))])
        r = self.run_apps("instalar", "copilot-cli", inp="si\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        link = os.path.join(self.home, ".local/bin/copilot")
        self.assertTrue(os.path.islink(link))
        self.assertEqual(subprocess.run([link], capture_output=True, text=True).stdout.strip(), "hola")
        self.run_apps("quitar", "copilot-cli")
        self.assertFalse(os.path.lexists(link))

    def test_malicious_tarball_rejected(self):
        publish("github/copilot-cli", "v6.6.6",
                [("copilot-linux-x64.tar.gz", make_tar([("../../escapado", b"x"), ("copilot", b"x")]))])
        r = self.run_apps("instalar", "copilot-cli", inp="si\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("archivo rechazado", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".local/escapado")))
        self.assertFalse(os.path.exists(os.path.join(self.home, "escapado")))


if __name__ == "__main__":
    try:
        unittest.main(verbosity=1)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
