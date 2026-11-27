"""On-demand x11vnc, bound to loopback and relayed over pinned agent HTTPS."""
import base64
import json
import os
import secrets
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

_thread = None
_identity = None
_stop = threading.Event()


def stop():
    _stop.set()


def sync(config, token, job, request):
    global _thread, _identity, _stop
    if not job:
        stop()
        return
    if _thread and _thread.is_alive():
        if _identity != job['id']:
            stop()
        return
    _stop = threading.Event()
    _identity = job['id']
    _thread = threading.Thread(target=run, args=(config, token, job, request, _stop), daemon=True)
    _thread.start()


def run(config, token, job, request, stopped):
    process = connection = None
    folder = None
    sequence = 1
    try:
        import pwd
        account = pwd.getpwnam('thinclient')
        if not shutil.which('x11vnc'):
            raise RuntimeError('x11vnc não instalado')
        # No server-supplied paths, display numbers, commands or network targets.
        folder = Path('/var/lib/freethinclient-client') / ('remote-' + secrets.token_hex(8))
        # The client may read its password but cannot replace paths used by root.
        folder.mkdir(mode=0o711)
        password_file = folder/'password'
        fd = os.open(password_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as output:
            os.fchown(output.fileno(), account.pw_uid, account.pw_gid)
            output.write(job['password']+'\n')
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
        command = ['x11vnc', '-display', ':0', '-auth', '/home/thinclient/.Xauthority',
                   '-localhost', '-rfbport', str(port), '-passwdfile', str(password_file),
                   '-once', '-nevershared', '-no6', '-noxdamage', '-quiet', '-timeout', '30', '-noclipboard']
        if not job.get('control'):
            command.append('-viewonly')
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, user=account.pw_uid, group=account.pw_gid,
                                   extra_groups=[], env={'HOME':account.pw_dir, 'PATH':'/usr/bin:/bin', 'DISPLAY':':0'})
        for _ in range(100):
            if stopped.is_set() or process.poll() is not None:
                raise RuntimeError('Sessão gráfica indisponível')
            try:
                connection = socket.create_connection(('127.0.0.1',port), timeout=0.1)
                break
            except OSError:
                time.sleep(0.05)
        if connection is None:
            raise RuntimeError('Tempo esgotado ao abrir x11vnc')
        connection.settimeout(0.05)
        deadline = min(float(job['expires']), time.time()+600)
        while not stopped.is_set() and time.time() < deadline:
            try:
                outgoing = connection.recv(256*1024)
                if not outgoing:
                    break
            except socket.timeout:
                outgoing = b''
            payload = dict(id=job['id'], key=job['key'], seq=sequence,
                           data=base64.b64encode(outgoing).decode(), state='connected')
            reply = None
            for attempt in range(3):
                try:
                    reply = json.loads(request(config, '/api/client/remote', payload, token))
                    break
                except OSError:
                    if stopped.wait(0.25):
                        break
            if not reply or reply.get('closed'):
                break
            sequence += 1
            incoming = base64.b64decode(reply.get('data',''), validate=True)
            if incoming:
                connection.settimeout(5)
                connection.sendall(incoming)
                connection.settimeout(0.05)
    except Exception:
        try:
            request(config, '/api/client/remote', dict(id=job['id'],key=job['key'],seq=sequence,state='error'), token)
        except Exception:
            pass
    finally:
        try:
            request(config, '/api/client/remote', dict(id=job['id'],key=job['key'],seq=sequence,state='closed'), token)
        except Exception:
            pass
        if connection:
            connection.close()
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
        if folder:
            shutil.rmtree(folder, ignore_errors=True)
