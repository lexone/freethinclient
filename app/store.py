"""SQLite state. Additive schema only; updater snapshots before changes."""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "state.db"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, ts INTEGER, actor TEXT, action TEXT);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA journal_mode=WAL")
            with db:
                yield db
        finally:
            db.close()

    def get(self, key, default=None):
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        with self.connect() as db:
            db.execute("INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (key, json.dumps(value, ensure_ascii=False)))

    def audit(self, actor, action):
        with self.connect() as db:
            db.execute("INSERT INTO audit(ts,actor,action) VALUES (?,?,?)", (int(time.time()), actor, action))

    def events(self):
        with self.connect() as db:
            rows = db.execute("SELECT ts,actor,action FROM audit ORDER BY id DESC LIMIT 100").fetchall()
        return [dict(zip(("ts", "actor", "action"), row)) for row in rows]
