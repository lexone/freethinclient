"""Authenticated control panel, served behind nginx. Python 3.12 on Ubuntu."""
import argparse
import base64
import hashlib
import http.cookies
import json
import os
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from app.security import password_ok, version_tuple
from app.store import Store, audit_peer
from app import fleet, users, images, remember, remote

BASE = Path(__file__).resolve().parents[1]
VERSION = (BASE / "VERSION").read_text().strip()
MAX_BODY = 8 * 1024 * 1024


def validate_profile(data):
    if not isinstance(data, dict):
        raise ValueError("Perfil inválido")
    result = {}
    for key, default in (("organization", "Minha empresa"), ("group", "Padrão"),
                         ("homepage", "https://www.google.com"), ("citrix_url", ""),
                         ("rdp_host", ""), ("rdp_domain", "")):
        value = data.get(key, default)
        if not isinstance(value, str) or len(value) > 512 or any(ord(c) < 32 for c in value):
            raise ValueError("Campo inválido: " + key)
        result[key] = value.strip()
    for key in ("homepage", "citrix_url"):
        if result[key]:
            url = urlsplit(result[key])
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise ValueError(key + " deve ser uma URL HTTPS sem credenciais")
    if result["rdp_host"] and not re.fullmatch(r"[A-Za-z0-9.:[\]_-]+", result["rdp_host"]):
        raise ValueError("Destino RDP inválido")
    result["lock_wallpaper"] = bool(data.get("lock_wallpaper", True))
    return result


class ControlServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, root, configuration):
        super().__init__(address, Handler)
        self.store = Store(root)
        fleet.initialize(self.store)
        users.initialize(self.store, configuration["admin_hash"])
        remember.initialize(self.store)
        self.remote = remote.Relay(self.store)
        self.configuration = configuration
        self.sessions = {}
        self.attempts = {}
        self.lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = "FreeThinClient"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # Paths may contain secrets. Log only response status via structured audit.
        pass

    def reply(self, status, value, *, mime="application/json", cookie=None):
        raw = json.dumps(value, ensure_ascii=False).encode() if mime == "application/json" else value
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(raw)

    def session(self, mutate=False):
        cookies = http.cookies.SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
            token = cookies["session"].value
        except (KeyError, http.cookies.CookieError):
            return None
        with self.server.lock:
            session = self.server.sessions.get(token) or remember.load(self.server.store, token)
            if not session or session["expires"] < time.time():
                self.server.sessions.pop(token, None)
                return None
        account = users.account(self.server.store, session['username'])
        if not account or not account['enabled'] or account['revision'] != session['revision']:
            with self.server.lock:
                self.server.sessions.pop(token, None)
            return None
        if mutate and not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), session["csrf"]):
            return None
        return session

    def do_GET(self):
        try:
            self.get()
        except (ValueError, OSError, json.JSONDecodeError):
            self.reply(500, {"error": "Falha ao ler o estado. Consulte o journal do serviço."})

    def get(self):
        path = urlsplit(self.path).path
        if path == "/healthz":
            with self.server.store.connect() as db:
                db.execute("SELECT 1").fetchone()
            return self.reply(200, {"status": "ok", "version": VERSION, "state_schema": 1})
        if path.startswith('/vendor/novnc/'):
            name = path.removeprefix('/vendor/novnc/')
            if not re.fullmatch(r'[A-Za-z0-9_./-]+', name) or '..' in name.split('/'):
                return self.reply(404, {'error':'Não encontrado'})
            file = BASE / 'web/vendor/novnc' / name
            if file.suffix != '.js' or not file.is_file():
                return self.reply(404, {'error':'Não encontrado'})
            return self.reply(200, file.read_bytes(), mime='text/javascript')
        if path.startswith('/assets/'):
            name = path.removeprefix('/assets/')
            if not re.fullmatch(r'[a-z0-9-]+\.svg', name):
                return self.reply(404, {'error': 'Não encontrado'})
            file = BASE / 'web' / 'assets' / name
            if not file.is_file():
                return self.reply(404, {'error': 'Não encontrado'})
            return self.reply(200, file.read_bytes(), mime='image/svg+xml')
        if path in ("/", "/index.html", "/app.js", "/fleet.js", "/images.js", "/shortcuts.js", "/network.js", "/remote.js", "/remote-channel.js", "/style.css", "/blue.css"):
            file = BASE / "web" / ("index.html" if path == "/" else path[1:])
            mime = "text/html; charset=utf-8" if file.suffix == ".html" else "text/javascript" if file.suffix == ".js" else "text/css"
            return self.reply(200, file.read_bytes(), mime=mime)
        session = self.session()
        if not session:
            return self.reply(401, {"error": "Entre no painel."})
        if path == '/api/images':
            if session['role'] != 'admin':
                return self.reply(403, {'error': 'Somente administradores gerenciam imagens'})
            return self.reply(200, images.snapshot(self.server.store, self.server.configuration))
        if path == '/api/users':
            if session['role'] != 'admin':
                return self.reply(403, {'error': 'Somente administradores gerenciam usuários'})
            return self.reply(200, {'users': users.listing(self.server.store)})
        if path == "/api/state":
            state = self.server.store
            status_path = Path(self.server.configuration["update_status"])
            update = json.loads(status_path.read_text()) if status_path.exists() else {"state": "idle"}
            request_path = Path(self.server.configuration['update_request'])
            if request_path.exists() and (not status_path.exists() or request_path.stat().st_mtime > status_path.stat().st_mtime):
                update = dict(update, state='queued', message='Na fila. Aguardando o serviço de atualização.')
            return self.reply(200, {"version": VERSION, "csrf": session["csrf"],
                                   "user": {"username": session["username"], "role": session["role"]},
                                   "repository": self.server.configuration["repository"],
                                   "profile": state.get("profile", validate_profile({})),
                                   "wallpaper": state.get("wallpaper"), "update": update,
                                   "events": state.events(), "pxe_ready": False})
        if path == '/api/fleet':
            return self.reply(200, {'groups': fleet.groups(self.server.store), 'devices': fleet.devices(self.server.store),
                                   'boot': self.boot_status()})
        if path == "/api/wallpaper":
            file = self.server.store.root / "wallpaper.bin"
            meta = self.server.store.get("wallpaper")
            if meta and file.exists():
                return self.reply(200, file.read_bytes(), mime=meta["mime"])
        return self.reply(404, {"error": "Não encontrado"})

    def do_POST(self):
        peer_token = audit_peer.set(self.headers.get('X-Real-IP', self.client_address[0])[:64])
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                self.close_connection = True
                return self.reply(413, {"error": "Corpo ausente ou maior que 8 MB"})
            if self.headers.get_content_type() != "application/json":
                return self.reply(415, {"error": "Use application/json"})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("Objeto JSON esperado")
            self.post(urlsplit(self.path).path, data)
        except (ValueError, KeyError, TypeError) as exc:
            self.reply(400, {"error": str(exc)[:200]})
        except OSError:
            self.reply(500, {"error": "Falha ao gravar. Consulte o journal do serviço."})

        finally:
            audit_peer.reset(peer_token)

    def post(self, path, data):
        if path == "/api/login":
            return self.login(data)
        if path == '/api/client/enroll':
            peer = self.headers.get('X-Real-IP', self.client_address[0])
            key, now = 'enroll:' + peer, time.time()
            with self.server.lock:
                start, count = self.server.attempts.get(key, (now, 0))
                if start < now - 900:
                    start, count = now, 0
                if count >= 20:
                    return self.reply(429, {'error': 'Muitas solicitações de cadastro. Aguarde 15 minutos.'})
                self.server.attempts[key] = (start, count + 1)
            return self.reply(201, fleet.enroll(self.server.store, data))
        if path == '/api/client/heartbeat':
            token = self.headers.get('Authorization', '').removeprefix('Bearer ')
            identity = fleet.authenticate(self.server.store, token)
            if not identity:
                return self.reply(401, {'error': 'Identidade do agente inválida'})
            result = fleet.heartbeat(self.server.store, identity, data)
            if result.get('approved'):
                meta = self.server.store.get('wallpaper')
                result['wallpaper'] = meta
                if 'dns_status' in data or 'remote_support' in data:
                    result['remote'] = self.server.remote.pending(identity, data.get('remote_support') == 1)
            return self.reply(200, result)
        if path == '/api/client/remote':
            token = self.headers.get('Authorization', '').removeprefix('Bearer ')
            identity = fleet.authenticate(self.server.store, token)
            if not identity:
                return self.reply(403, {'error':'Identidade do agente inválida'})
            return self.reply(200, self.server.remote.exchange(data, device=identity))
        if path == '/api/client/wallpaper':
            token = self.headers.get('Authorization', '').removeprefix('Bearer ')
            identity = fleet.authenticate(self.server.store, token)
            if not identity or not fleet.heartbeat(self.server.store, identity, {}).get('approved'):
                return self.reply(403, {'error': 'Máquina não aprovada'})
            file = self.server.store.root / 'wallpaper.bin'
            meta = self.server.store.get('wallpaper')
            if file.is_file() and meta:
                return self.reply(200, file.read_bytes(), mime=meta['mime'])
            return self.reply(404, {'error': 'Wallpaper não definido'})
        session = self.session(mutate=True)
        if not session:
            return self.reply(403, {"error": "Sessão ou proteção CSRF inválida"})
        state = self.server.store
        actor = session['username']
        if (path.startswith('/api/users/') or path.startswith('/api/update/') or path.startswith('/api/images/') or path.startswith('/api/remote/')) and session['role'] != 'admin':
            state.audit(actor, 'Acesso negado: ' + path)
            return self.reply(403, {'error': 'Esta ação exige um administrador'})
        if path == '/api/remote/start':
            return self.reply(201, self.server.remote.start(data.get('device'), actor, session['csrf'], data.get('control',False)))
        if path == '/api/remote/poll':
            return self.reply(200, self.server.remote.exchange(data, owner=session['csrf']))
        if path == '/api/remote/stop':
            self.server.remote.close(data.get('id'), session['csrf'])
            return self.reply(200, {'ok':True})
        if path == '/api/images/jobs':
            try:
                identity = images.enqueue(state, self.server.configuration, data, actor)
            except FileExistsError:
                return self.reply(409, {'error': 'Já existe uma tarefa de imagem em andamento'})
            return self.reply(202, {'ok': True, 'id': identity})
        if path == '/api/users/save':
            username = users.save(state, data, actor)
            return self.reply(200, {'ok': True, 'username': username})
        if path == '/api/groups/save':
            return self.reply(200, {'ok': True, 'id': fleet.save_group(state, data, actor)})
        if path == '/api/groups/delete':
            fleet.delete_group(state, fleet.text(data.get('id', ''), 40), actor)
            return self.reply(200, {'ok': True})
        if path == '/api/devices/assign':
            fleet.assign(state, data, actor)
            return self.reply(200, {'ok': True})
        if path == '/api/devices/command':
            fleet.command(state, data, actor)
            return self.reply(202, {'ok': True})
        if path == '/api/devices/delete':
            identity = fleet.text(data.get('id', ''), 40)
            with state.connect() as db:
                db.execute('DELETE FROM fleet_devices WHERE id=?', (identity,))
            state.audit(actor, 'Cadastro e credencial removidos: ' + identity)
            return self.reply(200, {'ok': True})
        if path == "/api/logout":
            state.audit(actor, "Logout do painel")
            self.server.remote.close_owner(session['csrf'])
            with self.server.lock:
                token = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))["session"].value
                self.server.sessions.pop(token, None)
                remember.revoke(state, token)
            return self.reply(200, {"ok": True}, cookie="session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0")
        if path == "/api/profile":
            profile = validate_profile({**state.get('profile', {}), **data})
            state.set("profile", profile)
            state.audit(actor, "Perfil salvo: " + profile["group"])
            return self.reply(200, {"ok": True})
        if path == "/api/wallpaper":
            raw = base64.b64decode(data.get("data", ""), validate=True)
            mime = "image/png" if raw.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg" if raw.startswith(b"\xff\xd8\xff") else None
            if not mime or len(raw) > 5 * 1024 * 1024:
                raise ValueError("Envie PNG ou JPEG de até 5 MB")
            target = state.root / "wallpaper.bin"
            temp = target.with_suffix(".tmp")
            temp.write_bytes(raw)
            os.replace(temp, target)
            state.set("wallpaper", {"mime": mime, "sha256": hashlib.sha256(raw).hexdigest()})
            state.audit(actor, "Wallpaper atualizado")
            return self.reply(200, {"ok": True})
        if path in ("/api/update/check", "/api/update/apply"):
            action = path.rsplit("/", 1)[1]
            job = {"action": action, "requested_at": int(time.time()), "actor": actor}
            if action == "apply":
                version_tuple(data.get("version"))
                job["version"] = data["version"]
            request_path = Path(self.server.configuration["update_request"])
            temporary = request_path.with_name("request-" + secrets.token_hex(8) + ".tmp")
            try:
                with temporary.open("x") as output:
                    json.dump(job, output)
                os.link(temporary, request_path)
            except FileExistsError:
                return self.reply(409, {"error": "Já existe uma solicitação em andamento"})
            finally:
                temporary.unlink(missing_ok=True)
            state.audit(actor, "Atualização solicitada: " + action)
            return self.reply(202, {"ok": True, "message": "Solicitação enviada ao serviço de atualização"})
        return self.reply(404, {"error": "Não encontrado"})

    def boot_status(self):
        root = Path(self.server.configuration.get('boot_root', '/srv/freethinclient/boot'))
        required = ('vmlinuz', 'initrd.img', 'filesystem.squashfs', 'boot.ipxe')
        return {'files': {name: (root / name).is_file() for name in required},
                'image_available': all((root / name).is_file() for name in required),
                'pxe_verified': False,
                'message': 'BIOS/UEFI e DHCP precisam de validação em um cliente real.'}

    def login(self, data):
        now = time.time()
        # nginx binds to TLS and overwrites this header. Direct backend is loopback-only.
        peer = self.headers.get("X-Real-IP", self.client_address[0])
        with self.server.lock:
            self.server.attempts = {k: v for k, v in self.server.attempts.items() if v[0] > now - 900}
            count = self.server.attempts.get(peer, (now, 0))[1]
            if count >= 10:
                return self.reply(429, {"error": "Muitas tentativas. Aguarde 15 minutos."})
            self.server.attempts[peer] = (now, count + 1)
        password = data.get("password", "")
        if not isinstance(password, str) or len(password) > 1024:
            raise ValueError("Senha inválida")
        account = users.account(self.server.store, data.get('username'))
        stored = account['password_hash'] if account else self.server.configuration['admin_hash']
        valid = password_ok(password, stored)
        if not account or not account['enabled'] or not valid:
            self.server.store.audit('anonymous', 'Tentativa de login recusada')
            return self.reply(401, {"error": "Usuário ou senha inválidos"})
        if type(data.get('remember', False)) is not bool:
            raise ValueError('Opção lembrar inválida')
        lifetime = remember.TTL if data.get('remember') else 3600
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.server.lock:
            self.server.attempts.pop(peer, None)
            self.server.sessions = {k: v for k, v in self.server.sessions.items() if v["expires"] > now}
            if len(self.server.sessions) >= 100:
                self.server.sessions.clear()
            self.server.sessions[token] = {"csrf": csrf, "expires": now + lifetime, "username": account["username"],
                                           "role": account["role"], "revision": account["revision"]}
        if data.get('remember'):
            remember.save(self.server.store, token, self.server.sessions[token])
        secure = "; Secure" if self.server.configuration.get("secure_cookie", True) else ""
        self.server.store.audit(account["username"], "Login no painel")
        return self.reply(200, {"ok": True, "csrf": csrf}, cookie=f"session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={lifetime}{secure}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/etc/freethinclient/panel.json")
    parser.add_argument("--data", default="/var/lib/freethinclient")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    ControlServer(("127.0.0.1", args.port), args.data, config).serve_forever()


if __name__ == "__main__":
    main()
