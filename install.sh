#!/usr/bin/env bash
# Run from a reviewed checkout: sudo bash install.sh --server-name IP_OU_DNS
set -Eeuo pipefail
umask 027
[[ $EUID -eq 0 ]] || { echo 'Execute com sudo.' >&2; exit 1; }
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 && "$(dpkg --print-architecture)" == amd64 ]] || {
  echo 'Requer Ubuntu Server 24.04 LTS amd64.' >&2; exit 1;
}
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SERVER_NAME=''
REPOSITORY='lexone/freethinclient'
while [[ $# -gt 0 ]]; do
  case "$1" in
    --server-name) SERVER_NAME=${2:?Informe IP ou DNS}; shift 2 ;;
    --repository) REPOSITORY=${2:?Informe dono/repositorio}; shift 2 ;;
    *) echo "Argumento desconhecido: $1" >&2; exit 1 ;;
  esac
done
[[ -n "$SERVER_NAME" ]] || { echo 'Uso: sudo bash install.sh --server-name IP_OU_DNS' >&2; exit 1; }
export SERVER_NAME REPOSITORY SOURCE
python3 - <<'PY'
import ipaddress,os,re
from pathlib import Path
from sys import path
path.insert(0,os.environ['SOURCE'])
from app.github import valid_repository
from app.security import version_tuple
valid_repository(os.environ['REPOSITORY'])
version_tuple((Path(os.environ['SOURCE'])/'VERSION').read_text().strip())
name=os.environ['SERVER_NAME']
try: ipaddress.ip_address(name)
except ValueError:
    if len(name)>253 or not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',label) for label in name.split('.')):
        raise SystemExit('IP ou DNS inválido')
PY
if [[ -f /etc/freethinclient/panel.json ]]; then
  echo 'Instalação existente preservada. Use o painel para atualizar ou docs/OPERACAO.md para alterar endereço.'
  exit 0
fi
[[ -f "$SOURCE/app/server.py" && -f "$SOURCE/web/index.html" ]] || { echo 'Checkout incompleto'; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 openssl nginx ca-certificates open-vm-tools
if ss -ltnH | awk '{print $4}' | grep -Eq ':(8080|8443)$'; then
  echo 'As portas 8080/8443 já estão em uso; instalação interrompida.' >&2; exit 1
fi
id freethinclient >/dev/null 2>&1 || useradd --system --home /var/lib/freethinclient --shell /usr/sbin/nologin freethinclient
install -d -m 0755 /opt/freethinclient /opt/freethinclient/releases /var/lib/freethinclient-update
install -d -m 0750 -o root -g freethinclient /etc/freethinclient
install -d -m 0750 -o freethinclient -g freethinclient /var/lib/freethinclient /var/lib/freethinclient/updates
install -d -m 0700 /var/backups/freethinclient /root/freethinclient-signing
VERSION=$(tr -d '\r\n' < "$SOURCE/VERSION")
DEST="/opt/freethinclient/releases/$VERSION-initial"
[[ ! -e "$DEST" ]] || { echo 'Release inicial já existe. Confira instalação parcial antes de repetir.' >&2; exit 1; }
install -d -m 0755 "$DEST"
cp -R "$SOURCE/app" "$SOURCE/web" "$SOURCE/client" "$SOURCE/scripts" "$SOURCE/deploy" "$SOURCE/docs" "$DEST/"
install -m 0644 "$SOURCE/VERSION" "$DEST/VERSION"
find "$DEST" -type d -name __pycache__ -prune -exec rm -rf -- {} +
chown -R root:root "$DEST"
find "$DEST" -type d -exec chmod 0755 {} +
find "$DEST" -type f -exec chmod 0644 {} +
ln -s "$DEST" /opt/freethinclient/current
# A signing key is unique to this initial installation. Private key NEVER enters git.
if [[ ! -f /root/freethinclient-signing/release-private.pem ]]; then
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out /root/freethinclient-signing/release-private.pem 2>/dev/null
fi
chmod 0600 /root/freethinclient-signing/release-private.pem
openssl pkey -in /root/freethinclient-signing/release-private.pem -pubout -out /etc/freethinclient/release-public.pem 2>/dev/null
chmod 0644 /etc/freethinclient/release-public.pem
python3 - <<'PY'
import ipaddress,json,os,secrets,subprocess,sys
from pathlib import Path
sys.path.insert(0,os.environ['SOURCE'])
from app.security import password_hash
password=secrets.token_urlsafe(20)
panel={'admin_hash':password_hash(password),'secure_cookie':True,'repository':os.environ['REPOSITORY'],
       'update_request':'/var/lib/freethinclient/updates/request.json',
       'update_status':'/var/lib/freethinclient-update/status.json'}
root=Path('/etc/freethinclient')
(root/'panel.json').write_text(json.dumps(panel,indent=2))
(root/'update.json').write_text(json.dumps({'repository':os.environ['REPOSITORY'],'github_token':'',
    'public_key':str(root/'release-public.pem')},indent=2))
(root/'update.json').chmod(0o600)
name=os.environ['SERVER_NAME']
try: ipaddress.ip_address(name); san='IP:'+name
except ValueError: san='DNS:'+name
subprocess.run(['openssl','req','-x509','-nodes','-newkey','rsa:3072','-days','365',
    '-keyout',str(root/'tls.key'),'-out',str(root/'tls.crt'),'-subj','/CN='+name,
    '-addext','subjectAltName='+san],check=True,capture_output=True)
(root/'tls.key').chmod(0o600)
# Show the generated password once. No plaintext credential file is retained.
print('\nUSUARIO DO PAINEL: admin\nSENHA INICIAL: '+password+'\nGuarde em seu gerenciador de senhas.\n')
PY
chown root:freethinclient /etc/freethinclient/panel.json
chmod 0640 /etc/freethinclient/panel.json
install -m 0644 "$SOURCE/deploy/freethinclient.service" /etc/systemd/system/
install -m 0644 "$SOURCE/deploy/freethinclient-update.service" /etc/systemd/system/
install -m 0644 "$SOURCE/deploy/freethinclient-update.timer" /etc/systemd/system/
install -m 0644 "$SOURCE/deploy/nginx.conf" /etc/nginx/conf.d/freethinclient.conf
nginx -t
systemctl daemon-reload
systemctl enable --now freethinclient.service freethinclient-update.timer
bash "$SOURCE/scripts/install-image-worker.sh"
systemctl enable nginx
systemctl reload-or-restart nginx
sleep 2
python3 - <<'PY'
import json,urllib.request
with urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=10) as response:
    assert json.load(response)['status']=='ok'
PY
echo "Painel: https://$SERVER_NAME:8443"
echo 'Certificado local criado. Substitua pela CA da empresa antes do uso em produção.'
echo 'PXE/DHCP não foram alterados. Libere TCP 8443 somente para a rede de administração.'
echo 'Para publicar releases assinadas, consulte docs/ATUALIZACOES.md.'
