#!/usr/bin/env bash
# Publish already-built artifacts; does NOT enable DHCP or ProxyDHCP.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Execute com sudo'; exit 1; }
ARTIFACTS=$(realpath -- "${1:?Uso: sudo bash scripts/setup-boot.sh /build/output IP_DA_VM}")
SERVER=${2:?Informe o IPv4 da VM de boot}
python3 - "$SERVER" <<'PY'
import ipaddress,sys
ipaddress.IPv4Address(sys.argv[1])
PY
for file in vmlinuz initrd.img filesystem.squashfs SHA256SUMS; do
  [[ -f "$ARTIFACTS/$file" ]] || { echo "Arquivo ausente: $file"; exit 1; }
done
(cd "$ARTIFACTS" && sha256sum -c SHA256SUMS)
apt-get update
apt-get install -y nginx tftpd-hpa ipxe
install -d -m 0755 /srv/freethinclient/boot /srv/tftp/freethinclient
for file in vmlinuz initrd.img filesystem.squashfs SHA256SUMS; do
  install -m 0644 "$ARTIFACTS/$file" /srv/freethinclient/boot/
done
[[ ! -f "$ARTIFACTS/freethinclient-blue-amd64.iso" ]] || install -m 0644 "$ARTIFACTS/freethinclient-blue-amd64.iso" /srv/freethinclient/boot/
cat > /srv/freethinclient/boot/boot.ipxe <<EOF
#!ipxe
# iPXE project: https://ipxe.org
dhcp
set base http://$SERVER:8081
kernel \${base}/vmlinuz initrd=initrd.magic boot=live quiet loglevel=3 components username=thinclient hostname=freethinclient locales=pt_BR.UTF-8 keyboard-layouts=br timezone=America/Sao_Paulo ip=dhcp fetch=\${base}/filesystem.squashfs nopersistence
initrd \${base}/initrd.img
boot
EOF
for filename in undionly.kpxe ipxe.efi; do
  source=$(find /usr/lib/ipxe -name "$filename" -print -quit)
  [[ -n "$source" ]] || { echo "Arquivo iPXE ausente: $filename"; exit 1; }
  install -m 0644 "$source" "/srv/tftp/freethinclient/$filename"
done
cat > /etc/nginx/conf.d/freethinclient-boot.conf <<'EOF'
server {
    listen 8081;
    server_name _;
    root /srv/freethinclient/boot;
    autoindex off;
    sendfile on;
    location / { try_files $uri =404; }
}
EOF
# Preserve an existing TFTP service. Its root must include /srv/tftp/freethinclient.
if [[ ! -f /etc/default/tftpd-hpa ]]; then
  printf '%s\n' 'TFTP_USERNAME="tftp"' 'TFTP_DIRECTORY="/srv/tftp"' 'TFTP_ADDRESS=":69"' 'TFTP_OPTIONS="--secure"' > /etc/default/tftpd-hpa
fi
nginx -t
systemctl enable --now tftpd-hpa
systemctl reload-or-restart nginx
echo "Arquivos publicados: http://$SERVER:8081/boot.ipxe"
echo 'Configure o DHCP/relay do piloto por arquitetura. Nenhuma concessão DHCP foi alterada.'
echo 'iPXE já carregado: chain http://IP:8081/boot.ipxe'
echo 'BIOS: freethinclient/undionly.kpxe; UEFI amd64: freethinclient/ipxe.efi.'
echo 'No DHCP, diferencie clientes iPXE para evitar loop de chainloading. Consulte docs/CLIENTES.md.'
