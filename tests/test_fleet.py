import json
import tempfile
import unittest
from app import fleet
from app.store import Store
import test_core


class FleetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        fleet.initialize(self.store)
        self.group = fleet.save_group(self.store, {'name': 'Laboratório', 'mode': 'kiosk'})

    def tearDown(self):
        self.temp.cleanup()

    def enroll(self, **fields):
        return fleet.enroll(self.store, {'mac':'02:00:00:00:00:01', 'name':'pc-01', 'firmware':'uefi', **fields})

    def test_approval_and_group_inheritance(self):
        client = self.enroll()
        self.assertFalse(fleet.heartbeat(self.store, client['id'], {})['approved'])
        fleet.assign(self.store, {'id':client['id'], 'group_id':self.group})
        state = fleet.heartbeat(self.store, client['id'], {'ip':'10.9.2.2'})
        self.assertEqual(state['profile']['mode'], 'kiosk')
        self.assertTrue(state['approved'])
        self.assertTrue(fleet.devices(self.store)[0]['online'])
        fleet.save_group(self.store, {'id':self.group, 'name':'Laboratório', 'mode':'desktop'})
        updated = fleet.heartbeat(self.store, client['id'], {})
        self.assertEqual(updated['profile']['mode'], 'desktop')
        self.assertNotEqual(state['revision'], updated['revision'])

    def test_tokens_are_scoped_and_never_listed(self):
        client = self.enroll()
        self.assertEqual(fleet.authenticate(self.store, client['token']), client['id'])
        self.assertIsNone(fleet.authenticate(self.store, 'wrong-token-not-authorized'))
        self.assertNotIn(client['token'], json.dumps(fleet.devices(self.store)))
        with self.store.connect() as db:
            token_hash = db.execute('SELECT token_hash FROM fleet_devices').fetchone()[0]
        self.assertNotEqual(token_hash, client['token'])

    def test_duplicate_enrollment_cannot_steal_identity(self):
        first = self.enroll()
        with self.assertRaises(ValueError):
            self.enroll()
        self.assertEqual(fleet.authenticate(self.store, first['token']), first['id'])

    def test_opt_in_diskless_reenrollment_rotates_token_only_after_offline(self):
        first = self.enroll()
        fleet.assign(self.store, {'id':first['id'], 'group_id':self.group})
        fleet.save_group(self.store, {'id':self.group,'name':'Laboratório','mac_reenroll':True})
        fleet.heartbeat(self.store, first['id'], {})
        with self.assertRaises(ValueError):
            self.enroll()
        with self.store.connect() as db:
            db.execute('UPDATE fleet_devices SET last_seen=1 WHERE id=?',(first['id'],))
        replacement = self.enroll()
        self.assertEqual(replacement['id'],first['id'])
        self.assertTrue(replacement['approved'])
        self.assertIsNone(fleet.authenticate(self.store,first['token']))
        self.assertEqual(fleet.authenticate(self.store,replacement['token']),first['id'])

    def test_command_acknowledgement_requires_matching_client(self):
        client = self.enroll()
        with self.assertRaises(ValueError):
            fleet.command(self.store, {'id':client['id'], 'action':'reboot'})
        fleet.assign(self.store, {'id':client['id'], 'group_id':self.group})
        fleet.command(self.store, {'id':client['id'], 'action':'reapply'})
        result = fleet.heartbeat(self.store, client['id'], {})
        self.assertEqual(result['command'], 'reapply')
        self.assertEqual(fleet.heartbeat(self.store, client['id'], {'ack':'wrong'})['command'], 'reapply')
        self.assertIsNone(fleet.heartbeat(self.store, client['id'], {'ack':result['command_id']})['command'])
        with self.assertRaises(ValueError):
            fleet.command(self.store, {'id':client['id'], 'action':'shell'})

    def test_group_deletion_is_blocked_with_assigned_devices(self):
        client = self.enroll()
        fleet.assign(self.store, {'id':client['id'], 'group_id':self.group})
        with self.assertRaises(ValueError):
            fleet.delete_group(self.store, self.group)
        self.assertEqual(len(fleet.groups(self.store)),1)

    def test_bad_urls_hosts_modes_and_booleans(self):
        for fields in ({'mode':'shell'}, {'homepage':'javascript:evil'}, {'homepage':'https://u:p@host'},
                       {'rdp_host':'-evil'}, {'rdp_host':'host;cmd'}, {'allow_usb':'false'},
                       {'mode':'citrix'}, {'mode':'rdp'}, {'boot_type':'format-disk'}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                fleet.validate_group({'name':'Test', **fields})

    def test_firmware_mismatch_prevents_applying_profile(self):
        fleet.save_group(self.store, {'id':self.group, 'name':'Laboratório', 'firmware':'bios'})
        client = self.enroll()
        fleet.assign(self.store, {'id':client['id'], 'group_id':self.group})
        self.assertFalse(fleet.heartbeat(self.store, client['id'], {})['approved'])

    def test_kiosk_target_validation_and_existing_group_defaults(self):
        old=fleet.validate_group({'name':'Existing'})
        self.assertFalse(old['show_system_icons'])
        self.assertTrue(old['show_browser'])
        self.assertEqual(old['kiosk_app'],'browser')
        for target, field, value in [('citrix','citrix_url','https://citrix.example'),('rdp','rdp_host','rdp.example')]:
            with self.assertRaises(ValueError):
                fleet.validate_group({'name':'Kiosk','mode':'kiosk','kiosk_app':target})
            profile=fleet.validate_group({'name':'Kiosk','mode':'kiosk','kiosk_app':target,field:value})
            self.assertEqual(profile['kiosk_app'],target)
        for field in ('show_browser','show_rdp','show_citrix','show_panel','show_system_icons','fullscreen'):
            with self.assertRaises(ValueError):
                fleet.validate_group({'name':'Invalid',field:'false'})
        with self.assertRaises(ValueError):
            fleet.validate_group({'name':'Invalid','kiosk_app':'shell'})

    def test_shortcuts_validation_and_partial_group_save(self):
        item={'id':'a'*12,'name':'Portal','url':'https://portal.example','icon':'browser','enabled':True}
        fleet.save_group(self.store,{'id':self.group,'shortcuts':[item],'show_shutdown':True,'browser_title':'Internet'})
        fleet.save_group(self.store,{'id':self.group,'description':'Nova descrição'})
        profile=next(group for group in fleet.groups(self.store) if group['id']==self.group)
        self.assertEqual(profile['shortcuts'],[item]);self.assertTrue(profile['show_shutdown'])
        self.assertEqual(profile['browser_title'],'Internet')
        for changes in ({'url':'javascript:alert(1)'},{'url':'https://user:pass@portal.example'},{'name':'bad\nname'},
                        {'id':'../evil'},{'icon':'../../etc/passwd'},{'enabled':'false'}):
            with self.assertRaises(ValueError):fleet.validate_group({'name':'Bad','shortcuts':[{**item,**changes}]})
        with self.assertRaises(ValueError):fleet.validate_group({'name':'Bad','shortcuts':[item,item]})
        with self.assertRaises(ValueError):fleet.validate_group({'name':'Bad','shortcuts':[item]*13})


class FleetApiTests(test_core.PanelTests):
    def test_client_token_cannot_read_admin_state_or_change_group(self):
        code, client = self.request('/api/client/enroll', {'mac':'02:00:00:00:00:02', 'name':'pc-02'})
        self.assertEqual(code,201)
        self.assertEqual(self.request('/api/fleet')[0],401)
        self.assertEqual(self.request('/api/groups/save',{'name':'bad'})[0],403)
        self.assertEqual(self.request('/api/client/heartbeat',{})[0],401)
        self.login()
        self.assertEqual(self.request('/api/groups/save',{'name':'Lab'},csrf=False)[0],403)
        code, group = self.request('/api/groups/save',{'name':'Lab'})
        self.assertEqual(code,200)
        self.assertEqual(self.request('/api/devices/assign',{'id':client['id'],'group_id':group['id']})[0],200)
        body = self.request('/api/fleet')[1]
        self.assertEqual(len(body['groups']),1)
        self.assertTrue(body['devices'][0]['approved'])
        self.assertNotIn('token',body['devices'][0])
