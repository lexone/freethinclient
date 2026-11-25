#!/usr/bin/env python3
"""Client agent. Runs as root; only fixed commands, never executes server strings."""
import hashlib
import json
import logging
import os
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path('/var/lib/freethinclient-client')
CONFIG = Path('/etc/freethinclient-client/config.json')
MAX_RESPONSE = 6 * 1024 * 1024


def atomic(path, data, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    with temp.open('wb') as output:
        os.chmod(temp, mode)
        output.write(data)
    os.replace(temp, path)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request(config, endpoint, data, token=''):
    # Trust the pinned enterprise/server certificate. Never disable validation.
    context = ssl.create_default_context(cafile=config['ca_file'])
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context), NoRedirect)
    req = urllib.request.Request(config['server'].rstrip('/') + endpoint, data=json.dumps(data).encode(), headers=headers)
    with opener.open(req, timeout=20) as response:
        raw = response.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise ValueError('Resposta maior que o limite')
    return raw


def primary_mac():
    route = subprocess.run(['ip', '-json', 'route', 'show', 'default'], check=True, capture_output=True, text=True)
    routes = json.loads(route.stdout)
    if not routes:
        raise ValueError('Nenhuma rota de rede disponível')
    interface = sorted(routes, key=lambda row: row.get('metric', 0))[0]['dev']
    return (Path('/sys/class/net') / interface / 'address').read_text().strip()


def client_ip():
    result = subprocess.run(['ip', '-json', 'address', 'show', 'scope', 'global'], check=True, capture_output=True, text=True)
    for interface in json.loads(result.stdout):
        for address in interface.get('addr_info', []):
            if address.get('family') == 'inet':
                return address['local']
    return ''


def tick(config):
    identity_path = ROOT / 'identity.json'
    if not identity_path.exists():
        identity = json.loads(request(config, '/api/client/enroll', {
            'mac': primary_mac(), 'name': socket.gethostname().split('.')[0],
            'firmware': 'uefi' if Path('/sys/firmware/efi').exists() else 'bios'}))
        atomic(identity_path, json.dumps(identity).encode())
    identity = json.loads(identity_path.read_text())
    ack_path = ROOT / 'ack'
    ack = ack_path.read_text().strip() if ack_path.exists() else ''
    response = json.loads(request(config, '/api/client/heartbeat', {'ip': client_ip(), 'ack': ack}, identity['token']))
    if not response.get('approved'):
        atomic(ROOT / 'profile.json', json.dumps({'approved': False}).encode(), 0o644)
        return
    profile = response['profile']
    wallpaper = response.get('wallpaper')
    if wallpaper:
        suffix = '.png' if wallpaper['mime'] == 'image/png' else '.jpg'
        path = ROOT / ('wallpaper-' + wallpaper['sha256'] + suffix)
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != wallpaper['sha256']:
            raw = request(config, '/api/client/wallpaper', {}, identity['token'])
            if hashlib.sha256(raw).hexdigest() != wallpaper['sha256']:
                raise ValueError('Wallpaper divergente')
            atomic(path, raw, 0o644)
        profile['wallpaper_path'] = str(path)
    profile.update(approved=True, device_name=response.get('device_name',socket.gethostname()), revision=response['revision'] + ':' + (wallpaper['sha256'] if wallpaper else 'blue'))
    if response.get('command') == 'reapply':
        profile['revision'] += ':' + response['command_id']
    atomic(ROOT / 'profile.json', json.dumps(profile).encode(), 0o644)
    action, command_id = response.get('command'), response.get('command_id')
    if action and command_id and ack != command_id:
        # Persist before requesting an ack so commands are not replayed after reboot.
        atomic(ack_path, command_id.encode())
        request(config, '/api/client/heartbeat', {'ack': command_id, 'ip': client_ip()}, identity['token'])
        if action in ('reboot', 'poweroff'):
            subprocess.run(['systemctl', action], check=True, timeout=20)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    ROOT.mkdir(parents=True, exist_ok=True)
    ROOT.chmod(0o755)  # profile is public; identity is private mode 0600.
    while True:
        try:
            if CONFIG.exists():
                config = json.loads(CONFIG.read_text())
                if not config.get('server', '').startswith('https://'):
                    raise ValueError('Servidor deve usar HTTPS')
                tick(config)
        except Exception as exc:
            logging.warning('Comunicação pendente: %s', type(exc).__name__)
        time.sleep(15)


if __name__ == '__main__':
    main()
