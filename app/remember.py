"""Persistent, revocable login tokens. Passwords are never stored here."""
import hashlib
import json
import time

TTL = 30 * 86400


def initialize(store):
    with store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS remembered_sessions (digest TEXT PRIMARY KEY, expires INTEGER, data TEXT)')
        db.execute('DELETE FROM remembered_sessions WHERE expires < ?', (time.time(),))


def save(store, token, session):
    with store.connect() as db:
        db.execute('DELETE FROM remembered_sessions WHERE expires < ?', (time.time(),))
        # Bound remembered devices per account, without invalidating other accounts.
        rows = db.execute('SELECT digest,data FROM remembered_sessions ORDER BY expires DESC').fetchall()
        own = [digest for digest, data in rows if json.loads(data)['username'] == session['username']]
        for digest in own[9:]:
            db.execute('DELETE FROM remembered_sessions WHERE digest=?', (digest,))
        db.execute('INSERT INTO remembered_sessions VALUES(?,?,?)',
                   (hashlib.sha256(token.encode()).hexdigest(), session['expires'], json.dumps(session)))


def load(store, token):
    if not isinstance(token, str) or len(token) > 100:
        return None
    with store.connect() as db:
        row = db.execute('SELECT data FROM remembered_sessions WHERE digest=? AND expires>?',
                         (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
    return json.loads(row[0]) if row else None


def revoke(store, token):
    with store.connect() as db:
        db.execute('DELETE FROM remembered_sessions WHERE digest=?', (hashlib.sha256(token.encode()).hexdigest(),))
