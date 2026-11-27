"""Unprivileged image-job API helpers. No commands or host paths come from the browser."""
import json
import os
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

CITRIX_HOSTS = ('downloads.citrix.com', 'downloads2.citrix.com', 'downloadplugins.citrix.com')
ACTIONS = ('inspect', 'client', 'linux', 'chromium', 'chrome', 'citrix', 'rollback')
BUSY = ('queued', 'preparing', 'updating', 'packing', 'publishing')


def validate(data):
    action = data.get('action')
    if action not in ACTIONS:
        raise ValueError('Ação de imagem inválida')
    result = {'action': action}
    if action == 'citrix':
        url, digest = data.get('url', ''), data.get('sha256', '')
        if not isinstance(url, str) or len(url) > 4096 or any(ord(c) < 32 for c in url):
            raise ValueError('URL Citrix inválida')
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.hostname not in CITRIX_HOSTS or parsed.port not in (None,443)
                or parsed.username or parsed.password or parsed.fragment or not parsed.path.lower().endswith('.deb')):
            raise ValueError('Use o link HTTPS direto de um .deb nos servidores oficiais Citrix')
        if not isinstance(digest, str) or not re.fullmatch('[a-fA-F0-9]{64}', digest):
            raise ValueError('Informe o SHA-256 do pacote Citrix')
        result.update(url=url, sha256=digest.lower())
    return result


def paths(store, config):
    return (store.root / 'image-jobs' / 'request.json',
            Path(config.get('image_status', '/var/lib/freethinclient-image/status.json')))


def snapshot(store, config):
    request, status = paths(store, config)
    result = json.loads(status.read_text()) if status.is_file() else {'state':'idle','step':0,
        'message':'Consulte a imagem publicada para obter as versões instaladas.'}
    result['queued'] = request.exists()
    result['worker_ready'] = Path(config.get('image_unit', '/etc/systemd/system/freethinclient-image.service')).is_file()
    log = status.parent / 'job.log'
    if log.is_file():
        with log.open('rb') as source:
            source.seek(max(0, log.stat().st_size - 24000))
            result['log'] = source.read(24000).decode('utf-8', errors='replace')
    else:
        result['log'] = ''
    return result


def enqueue(store, config, data, actor):
    job = validate(data)
    request, status = paths(store, config)
    if request.exists():
        raise FileExistsError('Já existe uma tarefa de imagem em andamento')
    job.update(id=secrets.token_hex(12),actor=actor,requested_at=int(time.time()))
    request.parent.mkdir(parents=True, exist_ok=True)
    temporary = request.with_name('request-' + secrets.token_hex(8) + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as output:
            json.dump(job, output)
        os.link(temporary, request)
    finally:
        temporary.unlink(missing_ok=True)
    store.audit(actor, 'Imagem PXE: solicitado ' + job['action'] + ' / tarefa ' + job['id'])
    return job['id']
