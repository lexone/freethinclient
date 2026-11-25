#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Execute como root.' >&2; exit 1; }
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
apt-get install -y squashfs-tools librsvg2-bin util-linux
install -d -m 0755 /srv/freethinclient/boot /var/lib/freethinclient-image
install -d -m 0750 -o freethinclient -g freethinclient /var/lib/freethinclient/image-jobs
install -m 0644 "$SOURCE/deploy/freethinclient-image.service" /etc/systemd/system/
install -m 0644 "$SOURCE/deploy/freethinclient-image.timer" /etc/systemd/system/
touch /opt/freethinclient/update.lock
systemctl daemon-reload
systemctl enable --now freethinclient-image.timer
