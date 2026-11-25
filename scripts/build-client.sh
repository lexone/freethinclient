#!/usr/bin/env bash
# Build a Debian 12 live ISO and PXE artifacts on an Ubuntu/Debian amd64 builder.
set -Eeuo pipefail
umask 022
[[ $EUID -eq 0 ]] || { echo 'Execute com sudo.' >&2; exit 1; }
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
SERVER=${1:?Uso: sudo bash scripts/build-client.sh https://IP:8443 /caminho/tls.crt /diretorio/novo}
CA=$(realpath -- "${2:?Informe o certificado/CA do painel}")
BUILD=${3:?Informe um diretório novo para o build}
[[ $(dpkg --print-architecture) == amd64 ]] || { echo 'Requer amd64'; exit 1; }
python3 - "$SERVER" <<'PY'
import sys
from urllib.parse import urlsplit
u=urlsplit(sys.argv[1])
if u.scheme!='https' or not u.hostname or u.username or u.password or u.path not in ('','/') or u.query or u.fragment:
    raise SystemExit('Use a origem HTTPS do painel, sem caminho nem credenciais')
PY
[[ -f "$CA" && ! -e "$BUILD" ]] || { echo 'CA ausente ou diretório de build já existe.'; exit 1; }
# Ubuntu ships an older, divergent live-build. Keep the BIOS/UEFI recipe
# on Debian 12 instead of dropping options or replacing host repositories.
source /etc/os-release
if [[ "$ID" != debian || "${VERSION_CODENAME:-}" != bookworm ]]; then
  exec bash "$SOURCE/scripts/build-client-isolated.sh" "$SERVER" "$CA" "$BUILD"
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y live-build debootstrap xorriso squashfs-tools isolinux syslinux-common grub-pc-bin grub-efi-amd64-bin mtools dosfstools cpio ca-certificates librsvg2-bin
mkdir -p -- "$BUILD"
cd -- "$BUILD"
BUILD=$PWD
lb config --mode debian --distribution bookworm --architecture amd64 \
  --binary-image iso-hybrid --bootloaders 'syslinux grub-efi' \
  --archive-areas 'main contrib non-free non-free-firmware' \
  --debian-installer none --apt-recommends false --uefi-secure-boot disable \
  --bootappend-live 'boot=live components username=thinclient hostname=freethinclient locales=pt_BR.UTF-8 keyboard-layouts=br timezone=America/Sao_Paulo nopersistence'
mkdir -p config/package-lists config/hooks/live
cat > config/package-lists/freethinclient.list.chroot <<'EOF'
linux-image-amd64
live-boot
live-config
live-config-systemd
systemd-sysv
xorg
xdg-user-dirs
lightdm
lightdm-gtk-greeter
xfce4
openbox
papirus-icon-theme
librsvg2-common
fonts-noto-core
chromium
freerdp2-x11
python3
python3-gi
gir1.2-gtk-3.0
zenity
network-manager
network-manager-gnome
iproute2
ca-certificates
curl
dbus-x11
gvfs
thunar-volman
firmware-linux-free
firmware-realtek
firmware-iwlwifi
locales
EOF
ROOT="$BUILD/config/includes.chroot"
install -d "$ROOT/usr/local/lib/freethinclient" "$ROOT/usr/share/freethinclient" \
  "$ROOT/etc/freethinclient-client" "$ROOT/etc/xdg/autostart" "$ROOT/etc/lightdm/lightdm.conf.d" \
  "$ROOT/etc/systemd/system/multi-user.target.wants" "$ROOT/var/lib/freethinclient-client" \
  "$ROOT/etc/skel/.config/xfce4/xfconf/xfce-perchannel-xml"
install -m 0644 "$SOURCE/client/agent.py" "$SOURCE/client/session.py" "$ROOT/usr/local/lib/freethinclient/"
install -m 0644 "$SOURCE/web/assets/"*.svg "$ROOT/usr/share/freethinclient/"
for name in blue-workspace browser remote citrix; do
  rsvg-convert -o "$ROOT/usr/share/freethinclient/$name.png" "$SOURCE/web/assets/$name.svg"
done
install -m 0644 "$SOURCE/client/kiosk.xml" "$ROOT/usr/share/freethinclient/"
install -m 0644 "$SOURCE/client/freethinclient.desktop" "$ROOT/etc/xdg/autostart/"
install -m 0644 "$SOURCE/client/freethinclient-client.service" "$ROOT/etc/systemd/system/"
ln -s ../freethinclient-client.service "$ROOT/etc/systemd/system/multi-user.target.wants/freethinclient-client.service"
install -m 0644 "$CA" "$ROOT/etc/freethinclient-client/ca.crt"
python3 - "$SERVER" "$ROOT" <<'PY'
import json,sys
from pathlib import Path
(Path(sys.argv[2])/'etc/freethinclient-client/config.json').write_text(json.dumps({'server':sys.argv[1], 'ca_file':'/etc/freethinclient-client/ca.crt'}))
PY
cat > "$ROOT/etc/lightdm/lightdm.conf.d/50-freethinclient.conf" <<'EOF'
[Seat:*]
autologin-user=thinclient
autologin-user-timeout=0
user-session=xfce
allow-guest=false
greeter-hide-users=true
EOF
cat > "$ROOT/etc/skel/.config/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xsettings" version="1.0"><property name="Net" type="empty"><property name="ThemeName" type="string" value="Adwaita-dark"/><property name="IconThemeName" type="string" value="Papirus-Dark"/></property></channel>
EOF
cat > config/hooks/live/0900-freethinclient.hook.chroot <<'EOF'
#!/bin/sh
set -eu
id thinclient >/dev/null 2>&1 || useradd -m -s /bin/bash -G audio,video,plugdev,netdev thinclient
passwd -l thinclient
# Never grant passwordless sudo to the public desktop account.
gpasswd -d thinclient sudo 2>/dev/null || true
rm -f /etc/sudoers.d/live
systemctl enable lightdm NetworkManager freethinclient-client
EOF
chmod 0755 config/hooks/live/0900-freethinclient.hook.chroot
if [[ ${FTC_BUILD_CONFIG_ONLY:-0} == 1 ]]; then
  echo 'Configuração validada com live-build do Debian 12. Nenhuma ISO foi gerada.'
  exit 0
fi
echo 'Gerando a imagem. Pode levar dezenas de minutos e vários GB de espaço.'
lb build 2>&1 | tee build.log
install -d "$BUILD/output"
ISO=$(find "$BUILD" -maxdepth 1 -name '*.iso' -print -quit)
[[ -n "$ISO" ]] || { echo 'ISO não encontrada'; exit 1; }
install -m 0644 "$ISO" "$BUILD/output/freethinclient-blue-amd64.iso"
KERNEL=$(find binary/live -maxdepth 1 -name 'vmlinuz*' -print -quit)
INITRD=$(find binary/live -maxdepth 1 -name 'initrd*' -print -quit)
install -m 0644 "$KERNEL" "$BUILD/output/vmlinuz"
install -m 0644 "$INITRD" "$BUILD/output/initrd.img"
install -m 0644 binary/live/filesystem.squashfs "$BUILD/output/filesystem.squashfs"
(cd output && sha256sum freethinclient-blue-amd64.iso vmlinuz initrd.img filesystem.squashfs > SHA256SUMS)
echo "Arquivos gerados em $BUILD/output. Homologue primeiro em uma VM cliente."
