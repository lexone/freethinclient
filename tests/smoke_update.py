"""Destructive integration test ONLY in the disposable CI container."""
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

if os.environ.get("FTC_DISPOSABLE_TEST") != "1" or not Path("/.dockerenv").exists():
    raise SystemExit("Este teste é exclusivo de um contêiner descartável do CI.")
sys.path.insert(0, "/opt/freethinclint/current")
from app import updater

subprocess.run(["systemctl", "stop", "freethinclint-update.timer"], check=True)
subprocess.run(["runuser", "-u", "freethinclint", "--", "python3", "-c",
                "from app.store import Store; Store('/var/lib/freethinclint').set('profile', {'organization':'CI persistence fixture'})"],
               cwd="/opt/freethinclint/current", check=True)


def package(root, version, broken=False):
    source = root / ("source-" + version)
    import shutil
    shutil.copytree("/opt/freethinclint/current", source)
    (source / "VERSION").write_text(version + "\n")
    if broken:
        (source / "app" / "server.py").write_text("raise RuntimeError('Intentional CI health failure')\n")
    archive = root / (version + ".tar.gz")
    with tarfile.open(archive, "w:gz") as output:
        for file in sorted(source.rglob("*")):
            if file.is_file() and "__pycache__" not in file.parts:
                output.add(file, arcname=file.relative_to(source).as_posix())
    raw = archive.read_bytes()
    return {"version": version, "asset": "fixture.tar.gz", "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}, raw


with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    manifest, raw = package(root, "0.1.1")
    updater.apply_update(manifest, lambda name, limit: raw)
    assert updater.healthy("0.1.1"), "Valid update failed"
    assert json.loads(updater.STATUS.read_text())["state"] == "updated"
    manifest, raw = package(root, "0.1.2", broken=True)
    try:
        updater.apply_update(manifest, lambda name, limit: raw)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Broken version should fail its health check")
    assert updater.healthy("0.1.1"), "Rollback did not restore working service"
    assert json.loads(updater.STATUS.read_text())["state"] == "rolled_back"
    assert not updater.PENDING.exists()
    result = subprocess.run(["runuser", "-u", "freethinclint", "--", "python3", "-c",
                             "from app.store import Store; assert Store('/var/lib/freethinclint').get('profile')['organization']=='CI persistence fixture'"],
                            cwd="/opt/freethinclint/current", check=True)
print("Real systemd update, database permissions, health failure and rollback passed.")
