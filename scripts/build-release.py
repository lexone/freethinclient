#!/usr/bin/env python3
"""Build and sign exact release bytes. No private key is copied into package."""
import argparse
import hashlib
import json
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.github import valid_repository
from app.security import version_tuple


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", required=True, type=Path)
    parser.add_argument("--repository", default="lexone/freethinclient")
    parser.add_argument("--minimum-version", default="0.1.0")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    version = (ROOT / "VERSION").read_text().strip()
    version_tuple(version)
    version_tuple(args.minimum_version)
    if version_tuple(args.minimum_version) > version_tuple(version):
        raise SystemExit("Versão mínima maior que a versão publicada")
    valid_repository(args.repository)
    args.output.mkdir(parents=True, exist_ok=True)
    package = args.output / f"freethinclient-{version}.tar.gz"
    with tarfile.open(package, "w:gz") as archive:
        for name in ("VERSION", "README.md", "CHANGELOG.md", "SECURITY.md", "install.sh", "app", "web", "scripts", "deploy", "docs", "tests"):
            path = ROOT / name
            files = sorted(path.rglob("*")) if path.is_dir() else [path]
            for file in files:
                if file.is_file() and not file.is_symlink() and "__pycache__" not in file.parts and file.suffix not in (".pyc", ".pem", ".key", ".env"):
                    archive.add(file, arcname=file.relative_to(ROOT).as_posix(), recursive=False)
    data = {"schema": 1, "repository": args.repository, "version": version,
            "minimum_version": args.minimum_version, "platform": "ubuntu-24.04-amd64", "state_schema": 1,
            "asset": package.name, "size": package.stat().st_size,
            "sha256": hashlib.sha256(package.read_bytes()).hexdigest()}
    manifest = args.output / "manifest.json"
    manifest.write_bytes((json.dumps(data, sort_keys=True, indent=2) + "\n").encode())
    subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(args.key), "-out",
                    str(args.output / "manifest.sig"), str(manifest)], check=True)
    print("Release criada:", package.name, "SHA-256:", data["sha256"])


if __name__ == "__main__":
    main()
