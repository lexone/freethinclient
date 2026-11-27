"""Bounded RFB relay over authenticated HTTPS polls; no inbound VNC ports.

The browser and the enrolled agent have separate credentials and can exchange
bytes only within one short-lived session. All state is lost on panel restart.
"""
import base64
import secrets
import threading
import time

CHUNK = 256 * 1024
BUFFER = 2 * 1024 * 1024
LIFETIME = 600


class Relay:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.sessions = {}

    def _device(self, identity):
        with self.store.connect() as db:
            row = db.execute('SELECT approved,last_seen FROM fleet_devices WHERE id=?', (identity,)).fetchone()
        return bool(row and row[0] and row[1] and row[1] > time.time() - 90)

    def _prune(self):
        now = time.time()
        for key, item in list(self.sessions.items()):
            if item['expires'] < now or item['browser_seen'] < now - 40:
                self._close(key, 'Sessão expirada ou navegador desconectado')

    def _close(self, identity, reason):
        item = self.sessions.pop(identity, None)
        if item:
            self.store.audit(item['actor'], 'Console remoto encerrado: ' + item['device'] + ' / ' + reason)

    def start(self, device, actor, owner, control=False):
        if not isinstance(device, str) or not self._device(device):
            raise ValueError('Selecione uma máquina aprovada e online')
        if type(control) is not bool:
            raise ValueError('Modo de controle inválido')
        with self.lock:
            self._prune()
            if any(item['device'] == device for item in self.sessions.values()):
                raise ValueError('Já existe um console aberto para esta máquina')
            if len(self.sessions) >= 4:
                raise ValueError('Limite de quatro consoles simultâneos')
            identity = secrets.token_hex(16)
            password = secrets.token_urlsafe(12)[:8]
            item = dict(device=device, actor=actor, owner=owner, control=control,
                        password=password, agent_key=secrets.token_urlsafe(32), expires=time.time()+LIFETIME,
                        browser_seen=time.time(), state='waiting', message='Aguardando o agente (até 15 segundos).',
                        to_agent=bytearray(), to_browser=bytearray(), browser_seq=0, agent_seq=0,
                        browser_reply=None, agent_reply=None)
            self.sessions[identity] = item
            self.store.audit(actor, 'Console remoto solicitado: ' + device + (' / controle' if control else ' / somente visualizar'))
            return dict(id=identity, password=password, expires=item['expires'], control=control)

    def pending(self, device, supported):
        with self.lock:
            self._prune()
            for identity, item in self.sessions.items():
                if item['device'] == device:
                    if not supported:
                        item.update(state='error', message='Atualize os componentes do cliente na imagem e reinicie o PC pelo PXE.')
                        return None
                    return dict(id=identity, key=item['agent_key'], password=item['password'],
                                expires=item['expires'], remaining=max(0, int(item['expires']-time.time())), control=item['control'])
        return None

    def close(self, identity, owner):
        with self.lock:
            item = self.sessions.get(identity)
            if item and not secrets.compare_digest(item['owner'], owner):
                raise ValueError('Console pertence a outra sessão')
            self._close(identity, 'Solicitado pelo administrador')

    def close_owner(self, owner):
        with self.lock:
            for identity, item in list(self.sessions.items()):
                if secrets.compare_digest(item['owner'], owner):
                    self._close(identity, 'Logout do painel')

    def exchange(self, data, *, device=None, owner=None):
        side = 'agent' if device is not None else 'browser'
        with self.lock:
            self._prune()
            item = self.sessions.get(data.get('id'))
            if not item:
                return dict(closed=True, message='Console encerrado ou expirado')
            if side == 'agent':
                if item['device'] != device or not secrets.compare_digest(str(data.get('key', '')), item['agent_key']):
                    raise ValueError('Credencial do console inválida')
            elif not secrets.compare_digest(item['owner'], owner or ''):
                raise ValueError('Console pertence a outra sessão')
            if not self._device(item['device']):
                self._close(data['id'], 'Máquina revogada ou offline')
                return dict(closed=True)
            if side == 'agent' and data.get('state') == 'closed':
                self._close(data['id'], 'Agente desconectado')
                return dict(closed=True)
            if side == 'browser':
                item['browser_seen'] = time.time()
            seq = data.get('seq')
            if type(seq) is not int or seq < 1:
                raise ValueError('Sequência inválida')
            # Retrying a timed-out POST never repeats keyboard bytes or loses a frame.
            if seq == item[side+'_seq']:
                return item[side+'_reply']
            if seq != item[side+'_seq'] + 1:
                raise ValueError('Sequência fora de ordem')
            encoded = data.get('data', '')
            if not isinstance(encoded, str) or len(encoded) > (CHUNK+2)//3*4:
                raise ValueError('Bloco excede o limite')
            raw = base64.b64decode(encoded, validate=True)
            if len(raw) > CHUNK:
                raise ValueError('Bloco excede o limite')
            incoming = item['to_browser' if side == 'agent' else 'to_agent']
            outgoing = item['to_agent' if side == 'agent' else 'to_browser']
            if len(incoming) + len(raw) > BUFFER:
                self._close(data['id'], 'Conexão lenta: limite de buffer')
                return dict(closed=True, message='Conexão lenta. Abra o console novamente.')
            incoming.extend(raw)
            if side == 'agent' and data.get('state') in ('connected', 'error'):
                item['state'] = data['state']
                item['message'] = ('Conectado' if data['state'] == 'connected' else
                                   'Não foi possível abrir a sessão gráfica. Confira o cliente e o pacote x11vnc.')
            block = bytes(outgoing[:CHUNK]); del outgoing[:CHUNK]
            reply = dict(data=base64.b64encode(block).decode(), state=item['state'],
                         message=item['message'], expires=item['expires'])
            item[side+'_seq'] = seq; item[side+'_reply'] = reply
            return reply
