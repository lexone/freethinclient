"""Named panel accounts; the installer admin is migrated once without changing its password."""
import re
from app.security import password_hash


def initialize(store, admin_hash):
    with store.connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS panel_users (
            username TEXT PRIMARY KEY, name TEXT NOT NULL, password_hash TEXT NOT NULL,
            role TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, revision INTEGER NOT NULL DEFAULT 1)""")
        db.execute("INSERT OR IGNORE INTO panel_users(username,name,password_hash,role) VALUES(?,?,?,?)",
                   ('admin', 'Administrador', admin_hash, 'admin'))


def account(store, username):
    if not isinstance(username, str):
        return None
    with store.connect() as db:
        row = db.execute('SELECT username,name,password_hash,role,enabled,revision FROM panel_users WHERE username=?',
                         (username.lower(),)).fetchone()
    return dict(zip(('username','name','password_hash','role','enabled','revision'), row)) if row else None


def listing(store):
    with store.connect() as db:
        rows = db.execute('SELECT username,name,role,enabled FROM panel_users ORDER BY username').fetchall()
    return [dict(zip(('username','name','role','enabled'), row)) for row in rows]


def save(store, data, actor):
    username = data.get('username', '')
    name, role = data.get('name', ''), data.get('role', 'operator')
    enabled, password = data.get('enabled', True), data.get('password', '')
    if not isinstance(username, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}', username):
        raise ValueError('Usuário inválido: use letras, números, ponto, hífen ou sublinhado')
    username = username.lower()
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 160 or any(ord(c) < 32 for c in name):
        raise ValueError('Informe o nome do usuário')
    if role not in ('admin', 'operator') or type(enabled) is not bool:
        raise ValueError('Permissão ou estado inválido')
    if not isinstance(password, str) or len(password) > 1024:
        raise ValueError('Senha inválida')
    digest = password_hash(password) if password else None
    with store.connect() as db:
        # Serialize last-admin validation and update, including concurrent requests.
        db.execute('BEGIN IMMEDIATE')
        old = db.execute('SELECT role,enabled FROM panel_users WHERE username=?', (username,)).fetchone()
        if not old and not digest:
            raise ValueError('Defina uma senha de pelo menos 12 caracteres')
        if old and old == ('admin', 1) and (role != 'admin' or not enabled):
            if db.execute("SELECT COUNT(*) FROM panel_users WHERE role='admin' AND enabled=1").fetchone()[0] <= 1:
                raise ValueError('Mantenha pelo menos um administrador ativo')
        if old:
            db.execute("""UPDATE panel_users SET name=?,role=?,enabled=?,
                password_hash=COALESCE(?,password_hash),revision=revision+1 WHERE username=?""",
                (name.strip(),role,int(enabled),digest,username))
        else:
            db.execute('INSERT INTO panel_users(username,name,password_hash,role,enabled) VALUES(?,?,?,?,?)',
                       (username,name.strip(),digest,role,int(enabled)))
    store.audit(actor, ('Usuário atualizado: ' if old else 'Usuário criado: ') + username +
                ' / ' + role + (' / ativo' if enabled else ' / desativado') + (' / senha definida' if digest else ''))
    return username
