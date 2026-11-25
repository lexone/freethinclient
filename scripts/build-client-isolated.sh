#!/usr/bin/env bash
# Ubuntu host -> signed Debian 12 bootstrap -> private mount namespace builder.
# No Docker daemon, host repository replacement, DHCP or firewall changes.
set -Eeuo pipefail
umask 022
[[ $EUID -eq 0 ]] || { echo 'Execute com sudo.' >&2; exit 1; }
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
SERVER=${1:?Informe a URL HTTPS do painel}
CA=$(realpath -- "${2:?Informe a CA pública do painel}")
BUILD=$(realpath -m -- "${3:?Informe um diretório novo de build}")
[[ -f "$CA" && ! -e "$BUILD" ]] || { echo 'CA ausente ou diretório de build já existe.' >&2; exit 1; }
[[ $(dpkg --print-architecture) == amd64 ]] || { echo 'Requer amd64.' >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y debootstrap debian-archive-keyring ca-certificates wget gpgv util-linux
install -d -m 0755 "$BUILD"
BUILDER="$BUILD/builder-root"
echo 'Preparando ambiente Debian 12 isolado para compatibilidade do live-build.'
# Require authenticated Debian Release metadata; never disable signature checks.
debootstrap --arch=amd64 --variant=minbase --include=ca-certificates \
  --force-check-gpg --keyring=/usr/share/keyrings/debian-archive-keyring.gpg \
  bookworm "$BUILDER" https://deb.debian.org/debian
install -d "$BUILDER/opt/freethinclient-source"
for name in scripts client web; do
  cp -R "$SOURCE/$name" "$BUILDER/opt/freethinclient-source/"
done
install -m 0644 "$CA" "$BUILDER/opt/freethinclient-ca.crt"
cp -L /etc/resolv.conf "$BUILDER/etc/resolv.conf"
# apt inside this build root must never start daemons in the host namespace.
printf '#!/bin/sh\nexit 101\n' > "$BUILDER/usr/sbin/policy-rc.d"
chmod 0755 "$BUILDER/usr/sbin/policy-rc.d"
export FTC_BUILD_CONFIG_ONLY=${FTC_BUILD_CONFIG_ONLY:-0}
# Namespace teardown removes remaining build mounts even when the build fails.
# --propagation private prevents propagation of nested live-build mounts to host.
unshare --mount --fork --kill-child --propagation private bash -s -- "$BUILDER" "$SERVER" <<'NAMESPACE'
set -Eeuo pipefail
BUILDER=$1
SERVER=$2
mount --rbind /dev "$BUILDER/dev"
mount --make-rslave "$BUILDER/dev"
mount -t proc proc "$BUILDER/proc"
mount --rbind /sys "$BUILDER/sys"
mount --make-rslave "$BUILDER/sys"
chroot "$BUILDER" /usr/bin/env DEBIAN_FRONTEND=noninteractive FTC_BUILD_CONFIG_ONLY="$FTC_BUILD_CONFIG_ONLY" \
  /bin/bash /opt/freethinclient-source/scripts/build-client.sh \
  "$SERVER" /opt/freethinclient-ca.crt /work
NAMESPACE
if [[ $FTC_BUILD_CONFIG_ONLY == 1 ]]; then
  echo "Configuração validada dentro do Debian 12: $BUILDER/work/config"
  exit 0
fi
install -d -m 0755 "$BUILD/output"
for file in freethinclient-blue-amd64.iso vmlinuz initrd.img filesystem.squashfs SHA256SUMS; do
  install -m 0644 "$BUILDER/work/output/$file" "$BUILD/output/"
done
(cd "$BUILD/output" && sha256sum -c SHA256SUMS)
echo "Arquivos gerados em $BUILD/output. Homologue primeiro em uma VM cliente."
