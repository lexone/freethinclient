#!/usr/bin/env bash
# Apply a reviewed checkout to an existing VM, preserving its credentials and state.
set -Eeuo pipefail
umask 027
[[ $EUID -eq 0 ]] || { echo 'Execute com sudo.' >&2; exit 1; }
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
[[ -f /etc/freethinclient/panel.json && -L /opt/freethinclient/current ]] || { echo 'Instalação existente não encontrada'; exit 1; }
ROOT=/opt/freethinclient
VERSION=$(tr -d '\r\n' < "$SOURCE/VERSION")
python3 - "$SOURCE" "$VERSION" <<'PY'
import sys
sys.path.insert(0,sys.argv[1])
from app.security import version_tuple
version_tuple(sys.argv[2])
PY
exec 9>"$ROOT/update.lock"
flock -n 9 || { echo 'Outra atualização está em andamento'; exit 1; }
[[ ! -f "$ROOT/pending-update.json" && ! -f /var/lib/freethinclient/updates/request.json ]] || { echo 'Há uma transação pendente. Resolva antes de aplicar o checkout.'; exit 1; }
PREVIOUS=$(readlink -f "$ROOT/current")
STAMP=$(date -u +%Y%m%d-%H%M%S)
DEST="$ROOT/releases/$VERSION-local-$STAMP"
BACKUP="/var/backups/freethinclient/local-$STAMP"
[[ ! -e "$DEST" && ! -e "$BACKUP" ]] || exit 1
install -d -m 0755 "$DEST"
for name in app web client scripts docs deploy; do
  cp -R "$SOURCE/$name" "$DEST/"
done
install -m 0644 "$SOURCE/VERSION" "$DEST/VERSION"
find "$DEST" -type d -name __pycache__ -prune -exec rm -rf -- {} +
chown -R root:root "$DEST"
find "$DEST" -type d -exec chmod 0755 {} +
find "$DEST" -type f -exec chmod 0644 {} +
python3 -m compileall -q "$DEST/app" "$DEST/client"
install -d -m 0700 "$BACKUP"
rollback() {
  trap - ERR
  echo 'Falha na aplicação. Restaurando versão anterior.' >&2
  systemctl stop freethinclient.service || true
  ln -sfn "$PREVIOUS" "$ROOT/current.rollback"
  mv -Tf "$ROOT/current.rollback" "$ROOT/current"
  if [[ -f "$BACKUP/state.db" ]]; then
    rm -f /var/lib/freethinclient/state.db-wal /var/lib/freethinclient/state.db-shm
    install -o freethinclient -g freethinclient -m 0640 "$BACKUP/state.db" /var/lib/freethinclient/state.db
  fi
  systemctl start freethinclient.service || true
  exit 1
}
trap rollback ERR
systemctl stop freethinclient.service
python3 - "$BACKUP" <<'PY'
import sqlite3,sys
from pathlib import Path
with sqlite3.connect('/var/lib/freethinclient/state.db') as source, sqlite3.connect(Path(sys.argv[1])/'state.db') as dest:
    source.backup(dest)
PY
ln -s "$DEST" "$ROOT/current.next"
mv -Tf "$ROOT/current.next" "$ROOT/current"
systemctl start freethinclient.service
python3 - "$VERSION" <<'PY'
import json,sys,time,urllib.request
for i in range(20):
    try:
        data=json.load(urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=2))
        if data['status']=='ok' and data['version']==sys.argv[1]: break
    except (OSError,ValueError): pass
    time.sleep(1)
else: raise SystemExit('Serviço não passou no teste de saúde')
PY
trap - ERR
echo "Versão $VERSION aplicada. Backup: $BACKUP"
echo 'Recarregue o painel com Ctrl+F5. A senha administrativa foi preservada.'
