"""Real Chrome/noVNC rendering against a deterministic RFB fixture over the relay.

Uses only a temporary local server/profile. Dependency: websocket-client==1.8.0
for the Chrome DevTools test driver (not a runtime application dependency).
"""
import argparse
import base64
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
if os.name=='nt':
    sys.path.insert(0,str(Path(tempfile.gettempdir())/'ftc-browser-deps'))
import websocket
from app.server import ControlServer, Handler
from app.security import password_hash
from app import fleet

HTML=b'''<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/style.css"><link rel="stylesheet" href="/blue.css"></head><body>
<dialog id="remote-dialog"><h2 id="remote-title"></h2><input type="checkbox" id="remote-control"><button id="remote-start">Conectar</button><button id="remote-close">Fechar</button><button id="remote-fullscreen">Tela inteira</button><p id="remote-status"></p><div id="remote-screen"></div></dialog><script type="module" src="/fixture.js"></script></body></html>'''
SCRIPT='''import '/remote.js';
import RFB from '/vendor/novnc/core/rfb.js';
const originalState=RFB.prototype._updateConnectionState;
RFB.prototype._updateConnectionState=function(...args){window.testRFB=this;return originalState.apply(this,args);};
window.testErrors=[];
window.addEventListener('error',event=>testErrors.push(event.message));
window.addEventListener('unhandledrejection',event=>testErrors.push(String(event.reason)));
let csrf='';
window.remoteApi=async(path,data)=>{const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(data)});const body=await response.json();if(!response.ok)throw Error(body.error);return body;};
try {const login=await remoteApi('/api/login',{username:'admin',password:'browser fixture password'});csrf=login.csrf;await openRemoteConsole({id:'__DEVICE__',name:'Fixture'});document.getElementById('remote-start').click();}
catch(error){testErrors.push(String(error));}
'''


class FixtureHandler(Handler):
    def get(self):
        if self.path=='/fixture':return self.reply(200,HTML,mime='text/html')
        if self.path=='/fixture.js':return self.reply(200,SCRIPT.replace('__DEVICE__',self.server.fixture_device).encode(),mime='text/javascript')
        return super().get()

    def post(self,path,data):
        if path=='/fixture/jpeg':
            self.server.fixture_jpeg_bytes=base64.b64decode(data['data'],validate=True)
            return self.reply(200,{'ok':True})
        return super().post(path,data)


def fake_agent(server, device, stopped):
    """Minimal authenticated RFB 3.8 server: red screen, VNC auth challenge."""
    active=None;seq=0;buf=bytearray();stage='version';out=b''
    fmt=(32,24,0,1,255,255,255,0,8,16)
    openssl_version=subprocess.check_output(['openssl','version'],text=True)
    providers=['-provider','default','-provider','legacy'] if openssl_version.startswith('OpenSSL 3.') else []
    while not stopped.wait(.01):
        pending=server.remote.pending(device,True)
        if not pending:continue
        if active!=pending['id']:
            active=pending['id'];seq=0;buf.clear();stage='version';out=b'RFB 003.008\n'
        seq+=1
        result=server.remote.exchange(dict(id=active,key=pending['key'],seq=seq,state='connected',data=base64.b64encode(out).decode()),device=device)
        out=b''
        if result.get('closed'):continue
        buf.extend(base64.b64decode(result.get('data','')))
        while buf:
            server.fixture_stage=stage
            if stage=='version':
                if len(buf)<12:break
                assert bytes(buf[:12])==b'RFB 003.008\n',bytes(buf[:12]);del buf[:12]
                out+=b'\x01\x02';stage='security'
            elif stage=='security':
                if len(buf)<1:break
                assert buf[0]==2;del buf[:1];out+=bytes(range(16));stage='authentication'
            elif stage=='authentication':
                if len(buf)<16:break
                # Validate noVNC's DES against OpenSSL rather than accepting any password.
                password=pending['password'].encode()[:8]
                key=bytes(int(f'{byte:08b}'[::-1],2) for byte in password)
                enc=subprocess.run(['openssl','enc','-des-ecb',*providers,'-K',key.hex(),'-nopad'],input=bytes(range(16)),capture_output=True,check=True).stdout
                assert bytes(buf[:16])==enc,'VNC challenge response mismatch';del buf[:16]
                out+=b'\0\0\0\0';stage='init'
            elif stage=='init':
                if len(buf)<1:break
                del buf[:1];name=b'Browser rendering fixture'
                out+=struct.pack('!HH',320,200)+struct.pack('!BBBBHHHBBBxxx',*fmt)+struct.pack('!I',len(name))+name
                stage='normal'
            else:
                kind=buf[0]
                if kind==0:
                    if len(buf)<20:break
                    fmt=struct.unpack('!BBBBHHHBBBxxx',buf[4:20]);del buf[:20]
                elif kind==2:
                    if len(buf)<4:break
                    size=4+struct.unpack('!H',buf[2:4])[0]*4
                    if len(buf)<size:break
                    del buf[:size]
                elif kind==3:
                    if len(buf)<10:break
                    del buf[:10]
                    value=255<<fmt[7]
                    pixel=value.to_bytes(fmt[0]//8,'big' if fmt[2] else 'little')
                    if server.fixture_jpeg:
                        jpeg=server.fixture_jpeg_bytes
                        length=len(jpeg);compact=bytearray()
                        for _ in range(2):
                            if length<128:break
                            compact.append((length&127)|128);length>>=7
                        compact.append(length)
                        out+=b'\0\0\0\x01'+struct.pack('!HHHHi',0,0,320,200,7)+b'\x90'+bytes(compact)+jpeg
                    else:
                        out+=b'\0\0\0\x01'+struct.pack('!HHHHi',0,0,320,200,0)+pixel*(320*200)
                    server.fixture_frames+=1
                elif kind==4:
                    if len(buf)<8:break
                    del buf[:8]
                elif kind==5:
                    if len(buf)<6:break
                    del buf[:6]
                elif kind==6:
                    if len(buf)<8:break
                    size=8+struct.unpack('!I',buf[4:8])[0]
                    if len(buf)<size:break
                    del buf[:size]
                elif kind==150:
                    if len(buf)<10:break
                    del buf[:10]
                else:raise AssertionError(('Unexpected RFB message',kind))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--chrome');parser.add_argument('--real-vnc',action='store_true');parser.add_argument('--jpeg',action='store_true');args=parser.parse_args()
    chrome=args.chrome or shutil.which('google-chrome') or shutil.which('chromium')
    if os.name=='nt':chrome=chrome or r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    if not chrome:raise SystemExit('Chrome is required')
    display=None
    if args.real_vnc:
        if os.name=='nt' or os.geteuid()!=0 or os.environ.get('GITHUB_ACTIONS')!='true':
            raise SystemExit('Real X11 fixture is restricted to a disposable GitHub runner')
        import pwd
        try:pwd.getpwnam('thinclient')
        except KeyError:subprocess.run(['useradd','-m','thinclient'],check=True)
        Path('/home/thinclient/.Xauthority').touch()
        subprocess.run(['chown','thinclient:thinclient','/home/thinclient/.Xauthority'],check=True)
        Path('/var/lib/freethinclient-client').mkdir(exist_ok=True)
        Path('/var/lib/freethinclient-client').chmod(0o755)
        display=subprocess.Popen(['runuser','-u','thinclient','--','Xvfb',':0','-screen','0','800x600x24','-ac','-noreset'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            if Path('/tmp/.X11-unix/X0').exists():break
            time.sleep(.05)
        subprocess.run(['runuser','-u','thinclient','--','xsetroot','-display',':0','-solid','#ff0000'],check=True)
        os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix='ftc-browser-') as tmp:
        server=ControlServer(('127.0.0.1',0),Path(tmp)/'state',dict(admin_hash=password_hash('browser fixture password'),secure_cookie=False))
        server.RequestHandlerClass=FixtureHandler
        group=fleet.save_group(server.store,{'name':'Browser fixture'})
        enrolled=fleet.enroll(server.store,dict(name='browser-fixture',mac='02:00:00:55:66:77'))
        device=enrolled['id']
        fleet.assign(server.store,dict(id=device,group_id=group));fleet.heartbeat(server.store,device,{})
        server.fixture_device=device;server.fixture_stage='waiting';server.fixture_frames=0
        server.fixture_jpeg=args.jpeg;server.fixture_jpeg_bytes=b''
        if args.jpeg:
            global SCRIPT
            SCRIPT=SCRIPT.replace("try {const login=", "try {const color=document.createElement('canvas');color.width=320;color.height=200;const ctx=color.getContext('2d');ctx.fillStyle='#ff0000';ctx.fillRect(0,0,320,200);await fetch('/fixture/jpeg',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({data:color.toDataURL('image/jpeg',0.9).split(',')[1]})});const login=")
        stopped=threading.Event()
        def real_agent():
            from client.remote import run
            def request(config,path,data,token):
                req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
                with urllib.request.urlopen(req,timeout=5) as response:return response.read()
            while not stopped.wait(.01):
                pending=server.remote.pending(device,True)
                if pending:run({},enrolled['token'],pending,request,stopped)
        threads=[threading.Thread(target=server.serve_forever,daemon=True),threading.Thread(target=real_agent if args.real_vnc else fake_agent,args=() if args.real_vnc else (server,device,stopped),daemon=True)]
        for thread in threads:thread.start()
        profile=Path(tmp)/'chrome'
        process=subprocess.Popen([chrome,'--headless=new','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+str(profile),'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        ws=None
        try:
            active=profile/'DevToolsActivePort';deadline=time.time()+20
            while not active.exists():
                assert process.poll() is None,'Chrome exited';assert time.time()<deadline,'Chrome did not start';time.sleep(.1)
            port=active.read_text().splitlines()[0]
            pages=json.load(urllib.request.urlopen('http://127.0.0.1:'+port+'/json'))
            page=next(page for page in pages if page['type']=='page')
            ws=websocket.create_connection(page['webSocketDebuggerUrl'],timeout=10,suppress_origin=True)
            number=0;errors=[]
            def cdp(method,params=None):
                nonlocal number
                number+=1;identity=number;ws.send(json.dumps(dict(id=identity,method=method,params=params or {})))
                while True:
                    data=json.loads(ws.recv())
                    if data.get('method')=='Runtime.exceptionThrown':errors.append(data['params']['exceptionDetails'].get('text'))
                    if data.get('method')=='Log.entryAdded' and data['params']['entry'].get('level')=='error':errors.append(data['params']['entry']['text'][:300])
                    if data.get('id')==identity:return data
            cdp('Runtime.enable');cdp('Log.enable');cdp('Page.navigate',{'url':f'http://127.0.0.1:{server.server_port}/fixture'})
            deadline=time.time()+20;result={}
            while time.time()<deadline:
                expression="JSON.stringify({status:document.getElementById('remote-status')?.textContent,errors:window.testErrors,connection:window.testRFB?._rfbConnectionState,init:window.testRFB?._rfbInitState,canvases:[...document.querySelectorAll('canvas')].map(c=>({width:c.width,height:c.height,pixel:[...c.getContext('2d').getImageData(10,10,1,1).data]}))})"
                raw=cdp('Runtime.evaluate',{'expression':expression,'returnByValue':True})
                value=raw.get('result',{}).get('result',{}).get('value')
                if value:result=json.loads(value)
                if any(c['pixel'][0]>245 and c['pixel'][1]<10 and c['pixel'][2]<10 for c in result.get('canvases',[])):
                    print('Real browser console passed: noVNC authentication, relay, canvas red pixels and live controller'+(' (Tight JPEG)' if args.jpeg else ''))
                    return
                time.sleep(.1)
            raise AssertionError(dict(result=result,protocol=server.fixture_stage,frames=server.fixture_frames,errors=errors))
        finally:
            stopped.set()
            if ws:
                try:ws.send(json.dumps(dict(id=999,method='Browser.close')))
                except Exception:pass
                ws.close()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            server.shutdown();server.server_close()
            for thread in threads:thread.join(5)
            if display:
                display.terminate()
                try:display.wait(timeout=3)
                except subprocess.TimeoutExpired:display.kill();display.wait()


if __name__=='__main__':main()
