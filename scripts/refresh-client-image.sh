#!/usr/bin/env bash
# Refresh the existing PXE SquashFS without reinstalling Debian or changing DHCP.
set -Eeuo pipefail
umask 022
[[ $EUID -eq 0 ]] || { echo 'Execute como root.' >&2; exit 1; }
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
BOOT=$(realpath -- "${1:-/srv/freethinclient/boot}")
[[ -f "$BOOT/filesystem.squashfs" && -f "$BOOT/vmlinuz" && -f "$BOOT/initrd.img" ]] || { echo 'Arquivos PXE não encontrados.' >&2; exit 1; }
exec 9>"$BOOT/client-image.lock"
flock -n 9 || { echo 'Outra atualização da imagem está em andamento.' >&2; exit 1; }
apt-get update
apt-get install -y squashfs-tools librsvg2-bin
WORK=$(mktemp -d /var/tmp/ftc-client-refresh.XXXXXX)
cleanup() { rm -rf -- "$WORK"; }
trap cleanup EXIT
unsquashfs -d "$WORK/root" "$BOOT/filesystem.squashfs"
ROOT="$WORK/root"
[[ -f "$ROOT/etc/debian_version" && -d "$ROOT/usr/local/lib/freethinclient" ]] || { echo 'Não é uma imagem cliente FreeThinClient.' >&2; exit 1; }
[[ ! -f "$ROOT/var/lib/freethinclient-client/identity.json" ]] || { echo 'A imagem contém identidade de um cliente. Use uma imagem limpa.' >&2; exit 1; }
install -m 0644 "$SOURCE/client/session.py" "$SOURCE/client/agent.py" "$SOURCE/client/device_info.py" "$SOURCE/client/launch_options.py" "$SOURCE/client/network.py" "$SOURCE/client/dns_config.py" "$ROOT/usr/local/lib/freethinclient/"
install -d -m 0755 "$ROOT/usr/share/freethinclient" "$ROOT/etc/xdg/autostart"
install -d "$ROOT/etc/polkit-1/rules.d" "$ROOT/etc/NetworkManager/conf.d"
install -m 0644 "$SOURCE/client/power.rules" "$ROOT/etc/polkit-1/rules.d/49-freethinclient-power.rules"
install -m 0644 "$SOURCE/client/network.rules" "$ROOT/etc/polkit-1/rules.d/10-freethinclient-network.rules"
install -d "$ROOT/etc/systemd/system"
install -m 0644 "$SOURCE/client/freethinclient-client.service" "$ROOT/etc/systemd/system/"
install -m 0644 "$SOURCE/client/kiosk.xml" "$ROOT/usr/share/freethinclient/"
install -m 0644 "$SOURCE/client/freethinclient-info.desktop" "$ROOT/etc/xdg/autostart/"
install -m 0644 "$SOURCE/client/freethinclient.desktop" "$ROOT/etc/xdg/autostart/"
for name in blue-workspace browser remote citrix shutdown restart network; do
  install -m 0644 "$SOURCE/web/assets/$name.svg" "$ROOT/usr/share/freethinclient/"
  rsvg-convert -o "$ROOT/usr/share/freethinclient/$name.png" "$SOURCE/web/assets/$name.svg"
done
python3 -m py_compile "$ROOT/usr/local/lib/freethinclient/session.py" "$ROOT/usr/local/lib/freethinclient/agent.py"
mksquashfs "$ROOT" "$WORK/filesystem.squashfs" -noappend -comp xz
unsquashfs -s "$WORK/filesystem.squashfs"
STAMP=$(date -u +%Y%m%d-%H%M%S)
BACKUP="/var/backups/freethinclient/pxe-$STAMP"
install -d -m 0700 "$BACKUP"
cp --reflink=auto "$BOOT/filesystem.squashfs" "$BACKUP/filesystem.squashfs"
[[ ! -f "$BOOT/SHA256SUMS" ]] || cp "$BOOT/SHA256SUMS" "$BACKUP/"
install -m 0644 "$WORK/filesystem.squashfs" "$BOOT/filesystem.squashfs.next"
mv -f -- "$BOOT/filesystem.squashfs.next" "$BOOT/filesystem.squashfs"
(cd "$BOOT" && sha256sum vmlinuz initrd.img filesystem.squashfs > SHA256SUMS.next && mv -f SHA256SUMS.next SHA256SUMS)
echo "Imagem PXE atualizada. Backup: $BACKUP"
echo 'Reinicie o cliente para usar a nova imagem. Kernel, initrd, DHCP e ISO não foram alterados.'
