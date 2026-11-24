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
sys.path.insert(0, "/opt/freethinclient/current")
from app import updater

subprocess.run(["systemctl", "stop", "freethinclient-update.timer"], check=True)
subprocess.run(["runuser", "-u", "freethinclient", "--", "python3", "-c",
                "from app.store import Store; Store('/var/lib/freethinclient').set('profile', {'organization':'CI persistence fixture'})"],
               cwd="/opt/freethinclient/current", check=True)


def package(root, version, broken=False):
    source = root / ("source-" + version)
    import shutil
    shutil.copytree("/opt/freethinclient/current", source)
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
    major, minor, patch = map(int, updater.current_version().split('.'))
    good_version = f'{major}.{minor}.{patch + 1}'
    bad_version = f'{major}.{minor}.{patch + 2}'
    manifest, raw = package(root, good_version)
    updater.apply_update(manifest, lambda name, limit: raw)
    assert updater.healthy(good_version), "Valid update failed"
    assert json.loads(updater.STATUS.read_text())["state"] == "updated"
    manifest, raw = package(root, bad_version, broken=True)
    try:
        updater.apply_update(manifest, lambda name, limit: raw)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Broken version should fail its health check")
    assert updater.healthy(good_version), "Rollback did not restore working service"
    assert json.loads(updater.STATUS.read_text())["state"] == "rolled_back"
    assert not updater.PENDING.exists()
    result = subprocess.run(["runuser", "-u", "freethinclient", "--", "python3", "-c",
                             "from app.store import Store; assert Store('/var/lib/freethinclient').get('profile')['organization']=='CI persistence fixture'"],
                            cwd="/opt/freethinclient/current", check=True)
print("Real systemd update, database permissions, health failure and rollback passed.")
