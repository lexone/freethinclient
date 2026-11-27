#!/usr/bin/env python3
"""Read-only verification of the stable GitHub release using the server's pinned key."""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import updater
from app.release import extract_package,validate_package,MAX_PACKAGE
from app.security import version_tuple


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path('/etc/freethinclient/update.json'))
    parser.add_argument('--expected-version')
    args=parser.parse_args()
    config=json.loads(args.config.read_text())
    with tempfile.TemporaryDirectory(prefix='ftc-verify-') as temporary:
        directory=Path(temporary)
        manifest,download=updater.candidate(config,directory)
        if args.expected_version and manifest['version']!=args.expected_version:
            raise ValueError('A release estável não é a versão esperada')
        package=directory/'package.tar.gz'
        package.write_bytes(download(manifest['asset'],MAX_PACKAGE))
        validate_package(package,manifest)
        extract_package(package,directory/'source',manifest['version'])
        public=subprocess.run(['openssl','pkey','-pubin','-in',config['public_key'],'-outform','DER'],
                              capture_output=True,check=True).stdout
        print(json.dumps({'version':manifest['version'],'installed':updater.current_version(),
              'newer':version_tuple(manifest['version'])>version_tuple(updater.current_version()),
              'signature_valid':True,'sha256_valid':True,'package_valid':True,
              'public_key_sha256':hashlib.sha256(public).hexdigest()},indent=2))


if __name__=='__main__':
    try: main()
    except (ValueError,RuntimeError,OSError,subprocess.SubprocessError) as error:
        raise SystemExit('Verificação falhou: '+(str(error) if isinstance(error,(ValueError,RuntimeError)) else type(error).__name__)) from None
