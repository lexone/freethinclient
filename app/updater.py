"""Privileged worker. Panel writes requests, never shell commands.

Only this process reads GitHub credentials or changes /opt. It runs on a timer,
serializes updates with flock and journals a pending transaction before switching.
"""
import json
from contextlib import closing
import os
import platform
import shutil
import sqlite3
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from app.github import github_get, valid_repository
from app.release import MAX_PACKAGE, extract_package, validate_package, verify_manifest
from app.security import version_tuple

ROOT = Path(os.environ.get("FTC_INSTALL_ROOT", "/opt/freethinclient"))
STATE = Path(os.environ.get("FTC_DATA_ROOT", "/var/lib/freethinclient"))
CONTROL = STATE / "updates"
STATUS = Path(os.environ.get("FTC_STATUS_ROOT", "/var/lib/freethinclient-update")) / "status.json"
CONFIG = Path(os.environ.get("FTC_UPDATE_CONFIG", "/etc/freethinclient/update.json"))
BACKUPS = Path(os.environ.get("FTC_BACKUP_ROOT", "/var/backups/freethinclient"))
PENDING = ROOT / "pending-update.json"


def atomic_json(path, value, mode=0o644):
    path = Path(path)
    temporary = path.with_name(path.name + ".new")
    with temporary.open("w") as output:
        os.chmod(temporary, mode)
        json.dump(value, output, ensure_ascii=False)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)
    if os.name == "posix":
        fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def status(state, **fields):
    atomic_json(STATUS, {"state": state, "timestamp": int(time.time()), **fields})


def systemctl(action):
    subprocess.run(["systemctl", action, "freethinclient.service"], check=True, timeout=45, capture_output=True)


def healthy(version):
    for _ in range(20):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8080/healthz", timeout=2) as response:
                data = json.load(response)
            if data.get("status") == "ok" and data.get("version") == version and data.get("state_schema") == 1:
                return True
        except (OSError, ValueError):
            pass
        time.sleep(1)
    return False


def switch(target):
    link = ROOT / "current.next"
    link.unlink(missing_ok=True)
    link.symlink_to(target, target_is_directory=True)
    os.replace(link, ROOT / "current")


def load_config():
    config = json.loads(CONFIG.read_text())
    valid_repository(config["repository"])
    return config


def current_version():
    return (ROOT / "current" / "VERSION").read_text().strip()


def candidate(config, directory):
    repo, token = config["repository"], config.get("github_token", "")
    release = github_get(f"/repos/{repo}/releases/latest", token)
    if release.get("draft") or release.get("prerelease"):
        raise ValueError("Somente releases estáveis são aceitas")
    assets = {}
    for asset in release.get("assets", []):
        name = asset["name"]
        if name in assets:
            raise ValueError("Release com nomes de assets duplicados")
        assets[name] = asset

    def download(name, limit):
        asset = assets.get(name)
        if not asset or type(asset.get("id")) is not int or asset.get("state") != "uploaded":
            raise ValueError("Release incompleta: " + name)
        if not 0 < asset.get("size", 0) <= limit:
            raise ValueError("Asset excede o tamanho permitido")
        return github_get(f"/repos/{repo}/releases/assets/{asset['id']}", token, binary=True, limit=limit)

    raw = download("manifest.json", 65536)
    signature = download("manifest.sig", 8192)
    manifest = verify_manifest(raw, signature, config["public_key"], directory, repo)
    if release.get("tag_name") != "v" + manifest["version"]:
        raise ValueError("Tag e versão assinada divergem")
    installed = current_version()
    if version_tuple(installed) < version_tuple(manifest["minimum_version"]):
        raise ValueError("Atualize primeiro para a versão mínima exigida")
    return manifest, download


def assert_platform():
    release = platform.freedesktop_os_release()
    if release.get("ID") != "ubuntu" or release.get("VERSION_ID") != "24.04" or platform.machine() not in ("x86_64", "amd64"):
        raise ValueError("Atualização disponível apenas para Ubuntu 24.04 amd64")


def recover():
    if not PENDING.exists():
        return False
    transaction = json.loads(PENDING.read_text())
    old = Path(transaction["previous"])
    if old.parent != ROOT / "releases" or not old.is_dir():
        raise ValueError("Transação pendente inválida; recuperação manual necessária")
    systemctl("stop")
    switch(old)
    backup = Path(transaction["backup"])
    if backup.parent != BACKUPS:
        raise ValueError("Backup fora do diretório esperado")
    # Restore only the DB; profile/wallpaper files are not migrated in schema 1.
    for suffix in ("-wal", "-shm"):
        (STATE / ("state.db" + suffix)).unlink(missing_ok=True)
    restored = ROOT / "restored.db"
    shutil.copy2(backup / "state.db", restored)
    if os.name == "posix":
        shutil.chown(restored, user="freethinclient", group="freethinclient")
    os.replace(restored, STATE / "state.db")
    systemctl("start")
    if not healthy((old / "VERSION").read_text().strip()):
        raise RuntimeError("Rollback iniciado, mas serviço não passou no teste de saúde")
    PENDING.unlink()
    status("rolled_back", message="Versão anterior restaurada", version=current_version())
    return True


def apply_update(manifest, download):
    assert_platform()
    if version_tuple(manifest["version"]) <= version_tuple(current_version()):
        raise ValueError("Downgrade ou reinstalação de versão bloqueados")
    if shutil.disk_usage(ROOT).free < 512 * 1024 * 1024 + (STATE / "state.db").stat().st_size * 2:
        raise ValueError("Espaço livre insuficiente para atualização e backup")
    previous = (ROOT / "current").resolve()
    with tempfile.TemporaryDirectory(prefix="ftc-stage-", dir=ROOT) as staging:
        staging = Path(staging)
        status("downloading", target=manifest["version"])
        package = staging / "package.tar.gz"
        package.write_bytes(download(manifest["asset"], MAX_PACKAGE))
        validate_package(package, manifest)
        extracted = staging / "release"
        extract_package(package, extracted, manifest["version"])
        subprocess.run(["python3", "-m", "compileall", "-q", str(extracted / "app")], check=True, timeout=30,
                       env={**os.environ, "PYTHONPYCACHEPREFIX": str(staging / "bytecode")})
        dest = ROOT / "releases" / (manifest["version"] + "-" + manifest["sha256"][:12])
        if dest.exists():
            raise ValueError("Destino já existe; confira tentativa anterior antes de repetir")
        shutil.move(str(extracted), dest)
    backup = BACKUPS / (time.strftime("%Y%m%d-%H%M%S") + "-" + manifest["version"])
    backup.mkdir(parents=True, mode=0o700)
    status("applying", target=manifest["version"])
    systemctl("stop")
    try:
        with closing(sqlite3.connect(STATE / "state.db")) as source, closing(sqlite3.connect(backup / "state.db")) as target:
            source.backup(target)
        for file in (STATE / "wallpaper.bin", Path("/etc/freethinclient/panel.json")):
            if file.exists():
                shutil.copy2(file, backup / file.name)
        atomic_json(PENDING, {"previous": str(previous), "backup": str(backup)}, 0o600)
        switch(dest)
        systemctl("start")
        if not healthy(manifest["version"]):
            raise RuntimeError("Nova versão não passou no teste de saúde")
        PENDING.unlink()
        status("updated", version=manifest["version"], backup=str(backup))
    except Exception:
        if PENDING.exists():
            recover()
        else:
            systemctl("start")
        raise


def run():
    CONTROL.mkdir(parents=True, exist_ok=True)
    # Linux only. Kept local so verifier/tests also work on Windows.
    import fcntl
    with (ROOT / "update.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        if recover():
            (CONTROL / "request.json").unlink(missing_ok=True)
            return
        request = CONTROL / "request.json"
        if not request.exists():
            return
        try:
            if request.stat().st_size > 2048 or request.is_symlink():
                raise ValueError("Solicitação inválida")
            fd = os.open(request, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd) as source:
                job = json.loads(source.read(2049))
            if job.get("action") not in ("check", "apply"):
                raise ValueError("Ação inválida")
            config = load_config()
            key = Path(config["public_key"])
            if not key.is_file():
                raise ValueError("Chave pública não configurada. Consulte docs/ATUALIZACOES.md")
            status("checking")
            with tempfile.TemporaryDirectory(prefix="ftc-check-", dir=ROOT) as directory:
                manifest, download = candidate(config, directory)
                newer = version_tuple(manifest["version"]) > version_tuple(current_version())
                if job["action"] == "check":
                    status("available" if newer else "current", current=current_version(),
                           version=manifest["version"], signature_valid=True)
                else:
                    if job.get("version") != manifest["version"] or not newer:
                        raise ValueError("Release mudou ou não é mais nova. Consulte novamente.")
                    apply_update(manifest, download)
        except Exception as exc:
            # No raw HTTP response, URL or token in status output.
            message = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__
            rolled_back = not PENDING.exists() and STATUS.exists() and json.loads(STATUS.read_text()).get("state") == "rolled_back"
            status("rolled_back" if rolled_back else "error", message=message[:300], version=current_version())
        finally:
            request.unlink(missing_ok=True)


if __name__ == "__main__":
    run()
