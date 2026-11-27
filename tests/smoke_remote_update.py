"""Use real GitHub assets and the panel API to update ONLY a disposable CI server."""
import argparse
import json
import os
import secrets
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

if os.environ.get('FTC_DISPOSABLE_TEST')!='1' or not Path('/.dockerenv').exists():
    raise SystemExit('Este teste é exclusivo de um contêiner descartável do CI.')
sys.path.insert(0,'/opt/freethinclient/current')
from app import updater,fleet,users
from app.store import Store

parser=argparse.ArgumentParser()
parser.add_argument('--version',required=True)
args=parser.parse_args()
subprocess.run(['systemctl','stop','freethinclient-update.timer'],check=True)
config=Path('/etc/freethinclient/update.json')
value=json.loads(config.read_text());value['github_token']=os.environ.get('FTC_GITHUB_TOKEN','')
config.write_text(json.dumps(value));config.chmod(0o600)
password=secrets.token_urlsafe(24)
seed="""import json,sys
from app import users,fleet
from app.store import Store
payload=json.load(sys.stdin);store=Store('/var/lib/freethinclient')
users.save(store,{'username':'release-test-admin','name':'Release validation','role':'admin','password':payload['password']},'ci')
users.save(store,{'username':'release-test-operator','name':'Release validation operator','role':'operator','password':payload['password']},'ci')
store.set('profile',{'organization':'Remote release persistence fixture'})
group=fleet.save_group(store,{'name':'Remote update fixture','mode':'desktop'},'ci')
client=fleet.enroll(store,{'name':'release-client','mac':'02:00:00:11:22:33'})
fleet.assign(store,{'id':client['id'],'group_id':group},'ci')
"""
subprocess.run(['runuser','-u','freethinclient','--','python3','-c',seed],input=json.dumps({'password':password}).encode(),
               cwd='/opt/freethinclient/current',check=True)
store=Store('/var/lib/freethinclient')
old_hash=users.account(store,'release-test-admin')['password_hash']
old_groups=fleet.groups(store)
old_devices=fleet.devices(store)
cookie='';csrf=''


def api(path,data=None):
    global cookie,csrf
    headers={'Cookie':cookie,'X-CSRF-Token':csrf}
    if data is not None:headers['Content-Type']='application/json'
    request=urllib.request.Request('http://127.0.0.1:8080'+path,
             data=json.dumps(data).encode() if data is not None else None,headers=headers)
    try: response=urllib.request.urlopen(request,timeout=10)
    except urllib.error.HTTPError as error: response=error
    with response:
        if response.headers.get('Set-Cookie'):cookie=response.headers['Set-Cookie'].split(';',1)[0]
        return response.status,json.load(response)


def login(username):
    global cookie,csrf
    cookie='';csrf=''
    code,body=api('/api/login',{'username':username,'password':password})
    assert code==200,(code,body)
    csrf=body['csrf']


login('release-test-operator')
assert api('/api/update/check',{})[0]==403,'Operators cannot trigger updates'
login('release-test-admin')
assert api('/api/update/check',{})[0]==202
subprocess.run(['systemctl','start','freethinclient-update.service'],check=True)
status=json.loads(updater.STATUS.read_text())
assert status['state']=='available',status
assert status['version']==args.version and status['signature_valid'] is True,status
print('Real GitHub release check passed: authenticated assets, pinned signature and newer version')
assert api('/api/update/apply',{'version':args.version})[0]==202
subprocess.run(['systemctl','start','freethinclient-update.service'],check=True)
status=json.loads(updater.STATUS.read_text())
assert status['state']=='updated',status
assert updater.healthy(args.version),'Published release did not pass health check'
assert not updater.PENDING.exists()
assert Path(status['backup'],'state.db').is_file()
assert users.account(store,'release-test-admin')['password_hash']==old_hash
assert store.get('profile')['organization']=='Remote release persistence fixture'
assert fleet.groups(store)==old_groups
assert fleet.devices(store)==old_devices
assert api('/api/state')[0]==401,'Old sessions must expire after restart'
login('release-test-admin')
assert api('/api/state')[1]['version']==args.version
assert api('/api/update/check',{})[0]==202
subprocess.run(['systemctl','start','freethinclient-update.service'],check=True)
status=json.loads(updater.STATUS.read_text())
assert status['state']=='current',status
print('Real GitHub remote update passed: panel API/CSRF/roles, signature, package, backup, restart, health, persistence and re-login')
