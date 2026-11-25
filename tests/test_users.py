import json
import sqlite3
import tempfile
from app import users
from app.security import password_hash, password_ok
from app.store import Store
import test_core


class UserApiTests(test_core.PanelTests):
    def create_operator(self):
        self.login()
        code, _ = self.request('/api/users/save', {'username':'operador', 'name':'Operador piloto',
                            'password':'senha longa operador', 'role':'operator', 'enabled':True})
        self.assertEqual(code, 200)
        admin_cookie, admin_csrf = self.cookie, self.csrf
        code, body = self.request('/api/login', {'username':'operador', 'password':'senha longa operador'})
        self.assertEqual(code, 200)
        self.csrf = body['csrf']
        return admin_cookie, admin_csrf

    def test_operator_authorization_and_attributed_audit(self):
        self.create_operator()
        self.assertEqual(self.request('/api/users')[0], 403)
        self.assertEqual(self.request('/api/users/save', {'username':'evil'})[0], 403)
        self.assertEqual(self.request('/api/update/check', {})[0], 403)
        self.assertEqual(self.request('/api/groups/save', {'name':'Grupo do operador'})[0], 200)
        self.assertEqual(self.request('/api/profile', {'organization':'Teste'})[0], 200)
        events = self.request('/api/state')[1]['events']
        event = next(e for e in events if e['action'] == 'Grupo salvo: Grupo do operador')
        self.assertEqual(event['actor'], 'operador')
        self.assertEqual(event['ip'], '127.0.0.1')
        self.assertNotIn('senha longa operador', json.dumps(events))

    def test_disabling_account_revokes_existing_session(self):
        admin_cookie, admin_csrf = self.create_operator()
        operator_cookie, operator_csrf = self.cookie, self.csrf
        self.cookie, self.csrf = admin_cookie, admin_csrf
        self.assertEqual(self.request('/api/users/save', {'username':'operador','name':'Operador',
                            'role':'operator','enabled':False})[0], 200)
        self.cookie, self.csrf = operator_cookie, operator_csrf
        self.assertEqual(self.request('/api/state')[0], 401)
        self.assertEqual(self.request('/api/login', {'username':'operador','password':'senha longa operador'})[0], 401)

    def test_password_reset_revokes_session_and_never_exposes_hash(self):
        admin_cookie, admin_csrf = self.create_operator()
        operator_cookie = self.cookie
        self.cookie, self.csrf = admin_cookie, admin_csrf
        self.assertEqual(self.request('/api/users/save', {'username':'operador','name':'Operador',
                        'role':'operator','enabled':True,'password':'nova senha muito longa'})[0], 200)
        body = json.dumps(self.request('/api/users')[1])
        self.assertNotIn('password', body)
        self.assertNotIn('scrypt', body)
        self.cookie = operator_cookie
        self.assertEqual(self.request('/api/state')[0], 401)
        self.assertEqual(self.request('/api/login', {'username':'operador','password':'senha longa operador'})[0], 401)
        self.assertEqual(self.request('/api/login', {'username':'operador','password':'nova senha muito longa'})[0], 200)

    def test_csrf_last_admin_and_validation(self):
        self.login()
        self.assertEqual(self.request('/api/users/save', {}, csrf=False)[0], 403)
        for data in ({'username':'admin','name':'Admin','role':'operator'},
                     {'username':'admin','name':'Admin','role':'admin','enabled':False},
                     {'username':'bad name','name':'Bad','password':'senha longa operador'},
                     {'username':'new','name':'New','password':'curta'},
                     {'username':'new','name':'New','role':'root','password':'senha longa operador'}):
            self.assertEqual(self.request('/api/users/save', data)[0], 400)
        self.assertEqual(self.request('/api/state')[0], 200)

    def test_migration_preserves_admin_and_historical_events(self):
        with tempfile.TemporaryDirectory() as root:
            with sqlite3.connect(root + '/state.db') as db:
                db.execute('CREATE TABLE audit(id INTEGER PRIMARY KEY, ts INTEGER, actor TEXT, action TEXT)')
                db.execute("INSERT INTO audit VALUES(1,1,'admin','histórico')")
            db.close()
            store = Store(root)
            digest = password_hash('senha original longa')
            users.initialize(store, digest)
            users.initialize(store, password_hash('outra senha diferente'))
            self.assertTrue(password_ok('senha original longa', users.account(store,'admin')['password_hash']))
            self.assertEqual(store.events()[0]['action'], 'histórico')
            self.assertEqual(store.events()[0]['ip'], '')
