"""Release verification. A checksum alone does not authenticate a release."""
import hashlib
import json
import re
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

from app.security import version_tuple

MAX_PACKAGE = 32 * 1024 * 1024
MAX_EXPANDED = 128 * 1024 * 1024


def verify_manifest(raw, signature, public_key, directory, repository):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"
    signature_path = directory / "manifest.sig"
    manifest_path.write_bytes(raw)
    signature_path.write_bytes(signature)
    result = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(public_key),
                             "-signature", str(signature_path), str(manifest_path)],
                            capture_output=True, timeout=15)
    if result.returncode:
        raise ValueError("Assinatura da release inválida")
    data = json.loads(raw)
    if data.get("schema") != 1 or data.get("repository") != repository:
        raise ValueError("Manifesto incompatível com o repositório")
    version_tuple(data.get("version"))
    version_tuple(data.get("minimum_version"))
    if data.get("platform") != "ubuntu-24.04-amd64" or data.get("state_schema") != 1:
        raise ValueError("Plataforma ou esquema de dados incompatível")
    if data.get("asset") != f"freethinclient-{data['version']}.tar.gz":
        raise ValueError("Nome do pacote inválido")
    if not re.fullmatch(r"[a-f0-9]{64}", data.get("sha256", "")):
        raise ValueError("SHA-256 inválido")
    if type(data.get("size")) is not int or not 0 < data["size"] <= MAX_PACKAGE:
        raise ValueError("Tamanho inválido")
    return data


def validate_package(path, manifest):
    path = Path(path)
    if path.stat().st_size != manifest["size"]:
        raise ValueError("Tamanho do pacote divergente")
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("SHA-256 do pacote divergente")


def extract_package(path, destination, version):
    """Extract only regular files/directories; never follow archive links."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        if len(members) > 2000 or sum(m.size for m in members) > MAX_EXPANDED:
            raise ValueError("Pacote expandido excede limites")
        seen = set()
        for member in members:
            name = PurePosixPath(member.name)
            if (name.is_absolute() or ".." in name.parts or "\\" in member.name or ":" in member.name
                    or not name.parts or not (member.isfile() or member.isdir()) or member.name in seen):
                raise ValueError("Caminho ou tipo inseguro no pacote")
            seen.add(member.name)
            target = destination.joinpath(*name.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open("xb") as output:
                    while chunk := source.read(65536):
                        output.write(chunk)
                target.chmod(0o644)
    if (destination / "VERSION").read_text().strip() != version:
        raise ValueError("Versão interna do pacote divergente")
    for required in ("app/server.py", "app/updater.py", "web/index.html"):
        if not (destination / required).is_file():
            raise ValueError("Pacote incompleto: " + required)
    destination.chmod(0o755)
    for directory in destination.rglob("*"):
        if directory.is_dir():
            directory.chmod(0o755)
