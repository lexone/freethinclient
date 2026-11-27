import base64
import tempfile
import time
import unittest
from unittest.mock import patch
from app import fleet, remote
from app.store import Store
import test_core


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        fleet.initialize(self.store)
        self.device = fleet.enroll(self.store, {'name':'test-pc','mac':'02:00:00:00:00:01'})['id']
        group = fleet.save_group(self.store, {'name':'Test'})
        fleet.assign(self.store, {'id':self.device,'group_id':group})
        fleet.heartbeat(self.store,self.device,{})
        self.relay = remote.Relay(self.store)
        self.job = self.relay.start(self.device,'admin','browser-secret')
        self.agent = self.relay.pending(self.device, True)

    def test_isolation_replay_and_bytes(self):
        with self.assertRaises(ValueError):
            self.relay.exchange(dict(id=self.job['id'],seq=1),owner='other-browser')
        with self.assertRaises(ValueError):
            self.relay.exchange(dict(id=self.job['id'],seq=1,key='bad'),device=self.device)
        payload=dict(id=self.job['id'],seq=1,data=base64.b64encode(b'RFB keyboard').decode())
        first=self.relay.exchange(payload,owner='browser-secret')
        self.assertEqual(first,self.relay.exchange(payload,owner='browser-secret'))
        reply=self.relay.exchange(dict(id=self.job['id'],seq=1,key=self.agent['key'],
                                        data=base64.b64encode(b'RFB screen').decode(),state='connected'),device=self.device)
        self.assertEqual(base64.b64decode(reply['data']),b'RFB keyboard')
        reply=self.relay.exchange(dict(id=self.job['id'],seq=2),owner='browser-secret')
        self.assertEqual(base64.b64decode(reply['data']),b'RFB screen')
        self.assertNotIn(self.agent['key'],str(self.store.events()))
        self.assertNotIn(self.job['password'],str(self.store.events()))
        with self.assertRaises(ValueError):
            self.relay.start(self.device,'other','other')

    def test_expiry_revocation_old_client_and_logout(self):
        self.relay.pending(self.device,False)
        reply=self.relay.exchange(dict(id=self.job['id'],seq=1),owner='browser-secret')
        self.assertEqual(reply['state'],'error')
        self.relay.close_owner('browser-secret')
        self.assertTrue(self.relay.exchange(dict(id=self.job['id'],seq=2),owner='browser-secret')['closed'])
        job=self.relay.start(self.device,'admin','secret2')
        with self.store.connect() as db:
            db.execute('UPDATE fleet_devices SET approved=0 WHERE id=?',(self.device,))
        self.assertTrue(self.relay.exchange(dict(id=job['id'],seq=1),owner='secret2')['closed'])
        with self.assertRaises(ValueError):self.relay.start(self.device,'admin','secret')

    def test_bounded_buffers_and_order(self):
        with self.assertRaises(ValueError):
            self.relay.exchange(dict(id=self.job['id'],seq=5),owner='browser-secret')
        with self.assertRaises(ValueError):
            self.relay.exchange(dict(id=self.job['id'],seq=1,data='a'*(remote.CHUNK*2)),owner='browser-secret')
        with patch('app.remote.time.time',return_value=time.time()+601):
            self.assertTrue(self.relay.exchange(dict(id=self.job['id'],seq=1),owner='browser-secret')['closed'])


class RemoteApiTests(test_core.PanelTests):
    def test_login_page_contains_controls_and_actual_ui_version(self):
        import urllib.request
        from app.server import VERSION
        with urllib.request.urlopen(self.url + '/') as response:
            page=response.read().decode()
        self.assertIn('content="'+VERSION+'"',page)
        self.assertNotIn('__FTC_UI_VERSION__',page)
        self.assertIn('id="remember-login"',page)
        self.assertIn('Manter conectado por 30 dias',page)

    def test_console_requires_admin_csrf_and_enrolled_agent(self):
        self.assertEqual(self.request('/api/remote/start',{'device':'anything'})[0],403)
        self.login()
        self.assertEqual(self.request('/api/remote/start',{'device':'anything'},csrf=False)[0],403)
        self.assertEqual(self.request('/api/remote/start',{'device':'anything'})[0],400)
        self.assertEqual(self.request('/api/client/remote',{'id':'anything','seq':1})[0],403)
        from app import users
        users.save(self.server.store,dict(username='operator',name='Operator',role='operator',password='long operator password'),'admin')
        _, body=self.request('/api/login',dict(username='operator',password='long operator password'))
        self.csrf=body['csrf']
        self.assertEqual(self.request('/api/remote/start',{'device':'anything'})[0],403)

    def test_remember_restart_logout_and_account_change(self):
        code,body=self.request('/api/login',dict(username='admin',password='senha longa para teste',remember=True))
        self.assertEqual(code,200);self.csrf=body['csrf']
        self.server.sessions.clear()
        self.assertEqual(self.request('/api/state')[0],200)
        from app import remember, users
        with self.server.store.connect() as db:
            row=db.execute('SELECT digest,data FROM remembered_sessions').fetchone()
        self.assertNotIn(self.cookie.split('=',1)[1],str(row))
        self.assertNotIn('senha longa para teste',str(row))
        self.assertEqual(self.request('/api/logout',{})[0],200)
        self.assertEqual(self.request('/api/state')[0],401)
        code,body=self.request('/api/login',dict(username='admin',password='senha longa para teste',remember=True))
        self.csrf=body['csrf'];self.server.sessions.clear()
        users.save(self.server.store,dict(username='admin',name='Admin',role='admin',password='new long admin password'),'admin')
        self.assertEqual(self.request('/api/state')[0],401)
        self.assertEqual(self.request('/api/login',dict(username='admin',password='new long admin password',remember='true'))[0],400)
