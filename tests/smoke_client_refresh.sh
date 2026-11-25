#!/usr/bin/env bash
# Disposable filesystem test; never uses a deployed client image.
set -Eeuo pipefail
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
WORK=$(mktemp -d /var/tmp/ftc-refresh-test.XXXXXX)
trap 'rm -rf -- "$WORK"' EXIT
mkdir -p "$WORK/root/etc/freethinclient-client" "$WORK/root/usr/local/lib/freethinclient" "$WORK/boot"
printf '12\n' > "$WORK/root/etc/debian_version"
printf 'public certificate fixture' > "$WORK/root/etc/freethinclient-client/ca.crt"
printf 'kernel fixture' > "$WORK/boot/vmlinuz"
printf 'initrd fixture' > "$WORK/boot/initrd.img"
printf 'boot script fixture' > "$WORK/boot/boot.ipxe"
(cd "$WORK/boot" && sha256sum vmlinuz initrd.img boot.ipxe > "$WORK/unchanged")
mksquashfs "$WORK/root" "$WORK/boot/filesystem.squashfs" -noappend -comp xz
bash "$SOURCE/scripts/refresh-client-image.sh" "$WORK/boot"
(cd "$WORK/boot" && sha256sum -c "$WORK/unchanged" && sha256sum -c SHA256SUMS)
unsquashfs -cat "$WORK/boot/filesystem.squashfs" usr/local/lib/freethinclient/session.py > "$WORK/session.py"
cmp "$SOURCE/client/session.py" "$WORK/session.py"
[[ $(unsquashfs -cat "$WORK/boot/filesystem.squashfs" etc/freethinclient-client/ca.crt) == 'public certificate fixture' ]]
unsquashfs -cat "$WORK/boot/filesystem.squashfs" usr/share/freethinclient/blue-workspace.png > "$WORK/wallpaper.png"
python3 - "$WORK/wallpaper.png" <<'PYTEST'
import sys
from pathlib import Path
assert Path(sys.argv[1]).read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
PYTEST
echo 'Client refresh smoke passed: scripts, PNG, CA and boot files verified.'
