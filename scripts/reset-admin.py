#!/usr/bin/env python3
import getpass
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.security import password_hash

if os.geteuid() != 0:
    raise SystemExit("Execute com sudo.")
password = getpass.getpass("Nova senha (mínimo 12 caracteres): ")
if password != getpass.getpass("Confirme: "):
    raise SystemExit("Senhas diferentes.")
path = Path("/etc/freethinclint/panel.json")
config = json.loads(path.read_text())
config["admin_hash"] = password_hash(password)
temporary = path.with_suffix(".new")
temporary.write_text(json.dumps(config, indent=2))
temporary.chmod(0o640)
import shutil
shutil.chown(temporary, user="root", group="freethinclint")
os.replace(temporary, path)
subprocess.run(["systemctl", "restart", "freethinclint"], check=True)
print("Senha alterada e sessões encerradas.")
