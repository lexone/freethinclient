"""Real x11vnc/RFB authentication and framebuffer through the HTTPS relay API.

Only a disposable systemd CI container is allowed. No deployed machine is used.
"""
import base64
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

if os.environ.get('FTC_DISPOSABLE_TEST') != '1' or not Path('/.dockerenv').exists():
    raise SystemExit('Teste exclusivo de contêiner descartável')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.server import ControlServer
from app.security import password_hash
from app import fleet
from client.remote import run

subprocess.run(['useradd','-m','thinclient'],check=True)
Path('/home/thinclient/.Xauthority').touch()
subprocess.run(['chown','thinclient:thinclient','/home/thinclient/.Xauthority'],check=True)
Path('/var/lib/freethinclient-client').mkdir(exist_ok=True)
display=subprocess.Popen(['runuser','-u','thinclient','--','Xvfb',':0','-screen','0','800x600x24','-ac'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    for _ in range(100):
        if Path('/tmp/.X11-unix/X0').exists():break
        time.sleep(.05)
    with tempfile.TemporaryDirectory() as directory:
        server=ControlServer(('127.0.0.1',0),directory,dict(admin_hash=password_hash('smoke console password'),secure_cookie=False))
        http=threading.Thread(target=server.serve_forever,daemon=True);http.start()
        base='http://127.0.0.1:'+str(server.server_port)
        cookie='';csrf=''
        def api(path,data,token=''):
            headers={'Content-Type':'application/json','Cookie':cookie,'X-CSRF-Token':csrf}
            if token:headers['Authorization']='Bearer '+token
            req=urllib.request.Request(base+path,data=json.dumps(data).encode(),headers=headers)
            with urllib.request.urlopen(req,timeout=5) as response:
                return response.read()
        req=urllib.request.Request(base+'/api/login',data=json.dumps(dict(username='admin',password='smoke console password')).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req) as response:
            cookie=response.headers['Set-Cookie'].split(';',1)[0];csrf=json.load(response)['csrf']
        group=fleet.save_group(server.store,{'name':'Console fixture'})
        device=fleet.enroll(server.store,{'name':'console-pc','mac':'02:00:00:66:77:88'})
        fleet.assign(server.store,dict(id=device['id'],group_id=group));fleet.heartbeat(server.store,device['id'],{})
        job=json.loads(api('/api/remote/start',dict(device=device['id'],control=False)))
        pending=server.remote.pending(device['id'],True)
        stopped=threading.Event()
        worker=threading.Thread(target=run,args=({},device['token'],pending,lambda config,path,data,token:api(path,data,token),stopped),daemon=True)
        worker.start()
        incoming=bytearray();seq=0
        def exchange(out=b''):
            global seq
            seq+=1
            result=json.loads(api('/api/remote/poll',dict(id=job['id'],seq=seq,data=base64.b64encode(out).decode())))
            assert not result.get('closed'),result
            assert result.get('state')!='error',result
            incoming.extend(base64.b64decode(result['data']))
        def read(size):
            deadline=time.time()+15
            while len(incoming)<size:
                assert time.time()<deadline,('Timed out waiting for RFB bytes',len(incoming),size)
                exchange();time.sleep(.02)
            data=bytes(incoming[:size]);del incoming[:size];return data
        assert read(12).startswith(b'RFB 003.')
        exchange(b'RFB 003.008\n')
        methods=read(read(1)[0]);assert 2 in methods,methods
        exchange(b'\x02');challenge=read(16)
        key=bytes(int(f'{byte:08b}'[::-1],2) for byte in job['password'].encode()[:8])
        encrypted=subprocess.run(['openssl','enc','-des-ecb','-provider','default','-provider','legacy','-K',key.hex(),'-nopad'],input=challenge,capture_output=True,check=True).stdout
        exchange(encrypted);assert read(4)==b'\0\0\0\0'
        exchange(b'\x01');header=read(24)
        width,height=struct.unpack('!HH',header[:4]);assert (width,height)==(800,600),(width,height)
        read(struct.unpack('!I',header[20:24])[0])
        # Request raw pixels for a small rectangle, exercising real screen bytes.
        exchange(b'\x02\0\0\x01'+struct.pack('!i',0)+b'\x03\0'+struct.pack('!HHHH',0,0,8,8))
        update=read(4);assert update[0]==0 and struct.unpack('!H',update[2:])[0]>0
        rect=read(12);x,y,w,h,encoding=struct.unpack('!HHHHi',rect)
        assert encoding==0 and w and h,(x,y,w,h,encoding)
        assert len(read(w*h*(header[4]//8)))>0
        api('/api/remote/stop',dict(id=job['id']))
        worker.join(5);assert not worker.is_alive(),'Agent must stop and remove password file'
        assert not list(Path('/var/lib/freethinclient-client').glob('remote-*'))
        server.shutdown();server.server_close();http.join()
        print('Real console passed: authenticated HTTP API, loopback x11vnc, VNC password handshake, framebuffer, stop and cleanup')
finally:
    display.terminate()
    try:display.wait(timeout=3)
    except subprocess.TimeoutExpired:display.kill();display.wait()
