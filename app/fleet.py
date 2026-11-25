"""Groups, device approval and least-privilege client credentials."""
import hashlib
import ipaddress
import json
import re
import secrets
import time
from urllib.parse import urlsplit

MODES = ('desktop', 'browser', 'kiosk', 'citrix', 'rdp')
BOOT_TYPES = ('pxe', 'local')


def text(value, maximum=160):
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValueError('Texto inválido')
    return value.strip()


def mac_address(value):
    value = text(value, 17).lower().replace('-', ':')
    if not re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', value) or int(value[:2], 16) & 1 or value == '00:00:00:00:00:00':
        raise ValueError('MAC inválido: informe o endereço físico da placa de rede')
    return value


def validate_group(data):
    if not isinstance(data, dict):
        raise ValueError('Grupo inválido')
    result = {key: text(data.get(key, default), 512 if key in ('homepage', 'citrix_url') else 160)
              for key, default in (('name', ''), ('description', ''), ('mode', 'desktop'),
                                   ('boot_type', 'pxe'), ('firmware', 'auto'), ('homepage', 'https://www.google.com'),
                                   ('citrix_url', ''), ('rdp_host', ''), ('rdp_domain', ''))}
    if not result['name']:
        raise ValueError('Informe o nome do grupo')
    if result['mode'] not in MODES or result['boot_type'] not in BOOT_TYPES or result['firmware'] not in ('auto', 'bios', 'uefi'):
        raise ValueError('Modo de sessão, boot ou firmware inválido')
    result['kiosk_app'] = data.get('kiosk_app', 'browser')
    if result['kiosk_app'] not in ('browser', 'citrix', 'rdp'):
        raise ValueError('Aplicativo do quiosque inválido')
    target = result['kiosk_app'] if result['mode'] == 'kiosk' else result['mode']
    for key in ('homepage', 'citrix_url'):
        if result[key]:
            url = urlsplit(result[key])
            if url.scheme != 'https' or not url.hostname or url.username or url.password or any(c in result[key] for c in ('\\', '\"')):
                raise ValueError(key + ' deve ser HTTPS sem credenciais')
    if result['rdp_host'] and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:[\]_-]{0,252}', result['rdp_host']):
        raise ValueError('Destino RDP inválido')
    if result['rdp_domain'] and not re.fullmatch(r'[A-Za-z0-9._-]{1,160}', result['rdp_domain']):
        raise ValueError('Domínio inválido')
    if target == 'browser' and not result['homepage']:
        raise ValueError('Informe a URL do navegador')
    if target == 'citrix' and not result['citrix_url']:
        raise ValueError('Informe o portal Citrix')
    if target == 'rdp' and not result['rdp_host']:
        raise ValueError('Informe o destino RDP')
    for key, default in (('lock_wallpaper', True), ('allow_usb', False), ('reconnect', True), ('mac_reenroll', False),
                         ('show_browser', True), ('show_rdp', True), ('show_citrix', True),
                         ('show_system_icons', False), ('show_panel', True), ('fullscreen', False),
                         ('show_shutdown', False), ('show_restart', False), ('confirm_power', True)):
        if type(data.get(key, default)) is not bool:
            raise ValueError('Opção inválida: ' + key)
        result[key] = data.get(key, default)
    for key,default in (('browser_title','Navegador'),('rdp_title','Área remota'),('citrix_title','Citrix')):
        result[key]=text(data.get(key,default),80)
        if not result[key]: raise ValueError('Informe o nome do atalho')
    shortcuts=data.get('shortcuts',[])
    if not isinstance(shortcuts,list) or len(shortcuts)>12:
        raise ValueError('Cadastre no máximo 12 atalhos por grupo')
    result['shortcuts']=[]; seen=set()
    for item in shortcuts:
        if not isinstance(item,dict): raise ValueError('Atalho inválido')
        identity=text(item.get('id',''),12) or secrets.token_hex(6)
        title=text(item.get('name',''),80); address=text(item.get('url',''),1024)
        icon=item.get('icon','browser'); enabled=item.get('enabled',True)
        url=urlsplit(address)
        if not re.fullmatch('[a-f0-9]{12}',identity) or identity in seen or not title or icon not in ('browser','remote','citrix') or type(enabled) is not bool:
            raise ValueError('Identificador, nome, ícone ou estado do atalho inválido')
        if url.scheme!='https' or not url.hostname or url.username or url.password or any(c in address for c in ('\\','"')):
            raise ValueError('O endereço do atalho deve usar HTTPS sem credenciais')
        seen.add(identity)
        result['shortcuts'].append({'id':identity,'name':title,'url':address,'icon':icon,'enabled':enabled})
    return result


def initialize(store):
    with store.connect() as db:
        db.executescript('''
          CREATE TABLE IF NOT EXISTS fleet_groups (
            id TEXT PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            profile TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1);
          CREATE TABLE IF NOT EXISTS fleet_devices (
            id TEXT PRIMARY KEY, mac TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
            token_hash TEXT NOT NULL, approved INTEGER NOT NULL DEFAULT 0,
            group_id TEXT REFERENCES fleet_groups(id), last_seen INTEGER,
            ip TEXT, firmware TEXT, command TEXT, command_id TEXT, last_ack TEXT);
        ''')


def groups(store):
    with store.connect() as db:
        rows = db.execute('SELECT id,profile,revision FROM fleet_groups ORDER BY name COLLATE NOCASE').fetchall()
    return [dict(json.loads(profile), id=identity, revision=revision) for identity, profile, revision in rows]


def save_group(store, data, actor='admin'):
    import sqlite3
    identity = text(data.get('id', ''), 40) or secrets.token_hex(12)
    if data.get('id'):
        with store.connect() as db:
            previous=db.execute('SELECT profile FROM fleet_groups WHERE id=?',(identity,)).fetchone()
        if not previous: raise ValueError('Grupo não encontrado')
        data={**json.loads(previous[0]),**data}
    profile = validate_group(data)
    try:
        with store.connect() as db:
            if data.get('id') and not db.execute('SELECT 1 FROM fleet_groups WHERE id=?', (identity,)).fetchone():
                raise ValueError('Grupo não encontrado')
            db.execute('''INSERT INTO fleet_groups(id,name,profile) VALUES(?,?,?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,profile=excluded.profile,revision=revision+1''',
                       (identity, profile['name'], json.dumps(profile)))
    except sqlite3.IntegrityError:
        raise ValueError('Já existe um grupo com esse nome') from None
    store.audit(actor, 'Grupo salvo: ' + profile['name'])
    return identity


def delete_group(store, identity, actor='admin'):
    with store.connect() as db:
        if db.execute('SELECT 1 FROM fleet_devices WHERE group_id=?', (identity,)).fetchone():
            raise ValueError('Mova as máquinas para outro grupo antes de excluir')
        db.execute('DELETE FROM fleet_groups WHERE id=?', (identity,))
    store.audit(actor, 'Grupo excluído: ' + identity)


def devices(store):
    with store.connect() as db:
        rows = db.execute('''SELECT id,mac,name,approved,group_id,last_seen,ip,firmware,command,command_id,last_ack
                             FROM fleet_devices ORDER BY name''').fetchall()
    keys = ('id', 'mac', 'name', 'approved', 'group_id', 'last_seen', 'ip', 'firmware', 'command', 'command_id', 'last_ack')
    return [dict(zip(keys, row), online=bool(row[5] and row[5] > time.time() - 90)) for row in rows]


def enroll(store, data):
    import sqlite3
    mac = mac_address(data.get('mac', ''))
    name = text(data.get('name', ''), 63)
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9-]{0,62}', name):
        raise ValueError('Nome da máquina inválido')
    firmware = data.get('firmware', 'unknown')
    if firmware not in ('bios', 'uefi', 'unknown'):
        raise ValueError('Firmware inválido')
    identity, token = secrets.token_hex(12), secrets.token_urlsafe(32)
    try:
        with store.connect() as db:
            existing = db.execute('SELECT id,approved,group_id,last_seen FROM fleet_devices WHERE mac=?', (mac,)).fetchone()
            if existing:
                group = db.execute('SELECT profile FROM fleet_groups WHERE id=?', (existing[2],)).fetchone() if existing[1] else None
                profile = json.loads(group[0]) if group else {}
                if (profile.get('mac_reenroll') and existing[1]
                        and (not existing[3] or existing[3] < time.time() - 90)
                        and profile.get('firmware') in ('auto', firmware)):
                    db.execute('UPDATE fleet_devices SET token_hash=?,firmware=?,last_seen=NULL,command=NULL,command_id=NULL,last_ack=NULL WHERE id=?',
                               (hashlib.sha256(token.encode()).hexdigest(), firmware, existing[0]))
                    return {'id':existing[0], 'token':token, 'approved':True}
                raise ValueError('MAC já cadastrado ou agente ainda ativo; recadastro automático exige opção no grupo e 90 segundos sem heartbeat')
            if db.execute('SELECT COUNT(*) FROM fleet_devices WHERE approved=0').fetchone()[0] >= 200:
                raise ValueError('Limite de solicitações pendentes atingido')
            db.execute('INSERT INTO fleet_devices(id,mac,name,token_hash,firmware) VALUES(?,?,?,?,?)',
                       (identity, mac, name, hashlib.sha256(token.encode()).hexdigest(), firmware))
    except sqlite3.IntegrityError:
        raise ValueError('MAC já cadastrado; preserve a identidade do agente ou remova o cadastro anterior no painel') from None
    store.audit('client', 'Máquina aguardando aprovação: ' + name + ' (' + mac + ')')
    return {'id': identity, 'token': token, 'approved': False}


def authenticate(store, token):
    if not isinstance(token, str) or not 20 <= len(token) <= 100:
        return None
    with store.connect() as db:
        row = db.execute('SELECT id FROM fleet_devices WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    return row[0] if row else None


def assign(store, data, actor='admin'):
    identity, group_id = text(data.get('id', ''), 40), text(data.get('group_id', ''), 40)
    name = text(data.get('name', ''), 63)
    if name and not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9-]{0,62}', name):
        raise ValueError('Nome inválido')
    with store.connect() as db:
        if not db.execute('SELECT 1 FROM fleet_groups WHERE id=?', (group_id,)).fetchone():
            raise ValueError('Selecione um grupo existente')
        cursor = db.execute('UPDATE fleet_devices SET group_id=?, approved=1, name=CASE WHEN ?=\'\' THEN name ELSE ? END WHERE id=?',
                            (group_id, name, name, identity))
        if not cursor.rowcount:
            raise ValueError('Máquina não encontrada')
    store.audit(actor, 'Máquina aprovada/vinculada: ' + identity + ' / grupo: ' + group_id + (' / nome: ' + name if name else ''))


def command(store, data, actor='admin'):
    action = data.get('action')
    if action not in ('reapply', 'reboot', 'poweroff'):
        raise ValueError('Comando inválido')
    identity = text(data.get('id', ''), 40)
    with store.connect() as db:
        row = db.execute('SELECT approved,command FROM fleet_devices WHERE id=?', (identity,)).fetchone()
        if not row or not row[0]:
            raise ValueError('Máquina não aprovada')
        if row[1]:
            raise ValueError('Aguarde o comando anterior ser confirmado pelo agente')
        db.execute('UPDATE fleet_devices SET command=?,command_id=? WHERE id=?', (action, secrets.token_hex(12), identity))
    store.audit(actor, 'Comando solicitado: ' + action + ' / ' + identity)


def heartbeat(store, identity, data):
    ip = text(data.get('ip', ''), 50)
    if ip:
        ipaddress.ip_address(ip)
    with store.connect() as db:
        row = db.execute('SELECT approved,group_id,command,command_id,firmware FROM fleet_devices WHERE id=?', (identity,)).fetchone()
        if not row:
            raise ValueError('Máquina não encontrada')
        approved, group_id, action, command_id, firmware = row
        if data.get('ack') and data['ack'] == command_id:
            db.execute('UPDATE fleet_devices SET command=NULL,command_id=NULL,last_ack=? WHERE id=?', (command_id, identity))
            action = command_id = None
        db.execute("UPDATE fleet_devices SET last_seen=?,ip=CASE WHEN ?='' THEN ip ELSE ? END WHERE id=?", (int(time.time()), ip, ip, identity))
        group = db.execute('SELECT profile,revision FROM fleet_groups WHERE id=?', (group_id,)).fetchone() if approved else None
    result = {'approved': bool(approved and group), 'command': action, 'command_id': command_id}
    if group:
        profile = json.loads(group[0])
        if profile['firmware'] != 'auto' and firmware != profile['firmware']:
            return dict(result, approved=False, error='Firmware diferente do definido no grupo')
        result.update(profile=profile, revision=str(group_id) + ':' + str(group[1]))
    return result
