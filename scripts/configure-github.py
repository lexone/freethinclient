#!/usr/bin/env python3
"""Run on the server as root, token read silently from a TTY."""
import getpass
import json
import os
from pathlib import Path

if os.geteuid() != 0:
    raise SystemExit("Execute com sudo.")
path = Path("/etc/freethinclient/update.json")
config = json.loads(path.read_text())
config["github_token"] = getpass.getpass("Token GitHub (Enter para acesso público sem token): ").strip()
temporary = path.with_suffix(".new")
temporary.write_text(json.dumps(config, indent=2))
temporary.chmod(0o600)
os.replace(temporary, path)
print("Configuração salva. O token não é disponibilizado ao painel nem aos clientes.")
