import importlib.util
import os
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


def module(name):
    spec = importlib.util.spec_from_file_location('client_' + name, Path(__file__).parents[1] / 'client' / (name + '.py'))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


agent = module('agent')
session = module('session')
device_info = module('device_info')


class ClientTests(unittest.TestCase):
    def test_agent_preserves_identity_and_never_runs_arbitrary_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identity = {'id':'abc','token':'individual-test-token'}
            config = {'server':'https://panel.example', 'ca_file':'unused'}
            profile = {'approved':True,'profile':{'mode':'desktop'},'revision':'group:1','command':None}
            with patch.object(agent,'ROOT',root), patch.object(agent,'primary_mac',return_value='02:00:00:00:00:01'), patch.object(agent,'client_ip',return_value='10.0.0.2'), patch.object(agent,'request',side_effect=[json.dumps(identity).encode(),json.dumps(profile).encode()]) as request:
                agent.tick(config)
                self.assertEqual(request.call_args_list[0].args[1],'/api/client/enroll')
                self.assertEqual(json.loads((root/'identity.json').read_text()),identity)
            profile.update(command='shell',command_id='unexpected')
            with patch.object(agent,'ROOT',root), patch.object(agent,'client_ip',return_value='10.0.0.2'), patch.object(agent,'request',return_value=json.dumps(profile).encode()) as request, patch.object(agent.subprocess,'run') as run:
                agent.tick(config)
                self.assertEqual(request.call_args_list[0].args[1],'/api/client/heartbeat')
                self.assertEqual(request.call_args_list[0].args[3],identity['token'])
                run.assert_not_called()

    def test_reboot_is_acknowledged_before_fixed_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'identity.json').write_text(json.dumps({'id':'abc','token':'individual-test-token'}))
            profile={'approved':True,'profile':{'mode':'desktop'},'revision':'group:1','command':'reboot','command_id':'job-123'}
            with patch.object(agent,'ROOT',root), patch.object(agent,'client_ip',return_value='10.0.0.2'), patch.object(agent,'request',return_value=json.dumps(profile).encode()) as request, patch.object(agent.subprocess,'run') as run:
                agent.tick({})
                self.assertEqual(request.call_args_list[-1].args[2]['ack'],'job-123')
                run.assert_called_once_with(['systemctl','reboot'],check=True,timeout=20)
                agent.tick({})
                self.assertEqual(run.call_count,1)

    def test_application_arguments_keep_passwords_out_of_command_line(self):
        with patch.object(session.shutil,'which',return_value='/usr/bin/chromium'):
            args=session.application({'homepage':'https://example.org'},'kiosk')
        self.assertIn('--kiosk',args)
        self.assertNotIn('--no-sandbox',args)
        self.assertEqual(args[-1],'https://example.org')
        args=session.application({'rdp_host':'rdp.example','rdp_domain':'UBEC'},'rdp')
        self.assertIn('/cert:deny',args)
        self.assertNotIn('/cert:ignore',args)
        self.assertFalse(any(arg.startswith('/p:') for arg in args))


    def test_kiosk_target_and_browser_fullscreen(self):
        with patch.object(session.shutil,'which',return_value='/usr/bin/chromium'):
            args=session.application({'kiosk_app':'citrix','citrix_url':'https://portal.example'},'kiosk')
            self.assertIn('--kiosk',args)
            self.assertEqual(args[-1],'https://portal.example')
            args=session.application({'homepage':'https://example.org','fullscreen':True},'browser')
            self.assertIn('--start-fullscreen',args)
            self.assertNotIn('--kiosk',args)
        args=session.application({'kiosk_app':'rdp','rdp_host':'rdp.example'},'kiosk')
        self.assertIn('/v:rdp.example',args)
        self.assertIn('/f',args)
        with patch.object(session.subprocess,'run') as prompt:
            prompt.return_value.returncode=1
            self.assertIsNone(session.launch({'kiosk_app':'rdp','rdp_host':'rdp.example'},'kiosk'))
            self.assertEqual(prompt.call_args.args[0][0],'zenity')

    def test_clean_desktop_only_removes_managed_shortcuts(self):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory)
            desktop=home/'Desktop';desktop.mkdir()
            (desktop/'citrix.desktop').write_text('managed')
            (desktop/'remote.desktop').write_text('managed')
            (desktop/'my-document.txt').write_text('personal')
            reply=session.subprocess.CompletedProcess([],0,stdout=b'',stderr=b'')
            with patch.object(session,'stop_component',return_value=True),patch.object(session,'HOME',home), patch.object(session,'desktop_directory',return_value=desktop), patch.object(session,'call',return_value=reply) as command:
                session.apply_desktop({'show_browser':True,'show_rdp':False,'show_citrix':False})
                self.assertTrue((desktop/'browser.desktop').exists())
                self.assertIn('browser.png',(desktop/'browser.desktop').read_text())
                self.assertFalse((desktop/'citrix.desktop').exists())
                self.assertFalse((desktop/'remote.desktop').exists())
                self.assertTrue((desktop/'my-document.txt').exists())
                calls=[c.args[0] for c in command.call_args_list]
                self.assertTrue(any('/desktop-icons/file-icons/show-filesystem' in c and 'false' in c for c in calls))
                self.assertTrue(any('blue-workspace.png' in ' '.join(c) for c in calls),'wallpaper must be set even when xfconf has no existing keys')
                self.assertTrue(any('p=10;x=0;y=0' in c for c in calls))
                session.apply_desktop({'show_browser':False,'show_rdp':False,'show_citrix':False})
                self.assertFalse((desktop/'browser.desktop').exists())

    def test_kiosk_shell_has_no_desktop_or_panel(self):
        reply=session.subprocess.CompletedProcess([],0,stdout=b'',stderr=b'')
        with patch.object(session.os,'getuid',return_value=1000,create=True), patch.object(session,'call',return_value=reply) as command, patch.object(session.subprocess,'Popen') as spawn:
            session.session_shell({'mode':'kiosk'})
            self.assertIn(['xfce4-panel','--quit'],[c.args[0] for c in command.call_args_list])
            self.assertEqual(spawn.call_args.args[0][0],'openbox')

    def test_localized_desktop_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory)
            reply=session.subprocess.CompletedProcess([],0,stdout=str(home/'Área de trabalho').encode(),stderr=b'')
            with patch.object(session,'HOME',home),patch.object(session.shutil,'which',return_value='xdg-user-dir'),patch.object(session,'call',return_value=reply):
                self.assertEqual(session.desktop_directory(),home/'Área de trabalho')

    def test_desktop_helper_timeout_does_not_abort_session(self):
        with patch.object(session.subprocess,'run',side_effect=session.subprocess.TimeoutExpired('gio',10)):
            self.assertEqual(session.call(['gio','set']).returncode,1)

    def test_managed_launcher_has_xfce_checksum_for_exact_file_bytes(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(session,'desktop_directory',return_value=Path(directory)), patch.object(session,'call') as command:
                session.desktop_file('browser','Navegador','browser.png','browser')
                file=Path(directory)/'browser.desktop'
                digest=hashlib.sha256(file.read_bytes()).hexdigest()
                command.assert_called_once_with(['gio','set','-t','string',str(file),'metadata::xfce-exe-checksum',digest])
                if os.name == "posix":
                    self.assertTrue(file.stat().st_mode & 0o100)

    def test_custom_shortcuts_open_only_enabled_profile_entries(self):
        profile={'shortcuts':[{'id':'a'*12,'name':'Portal','url':'https://portal.example','icon':'browser','enabled':True}]}
        with patch.object(session.shutil,'which',return_value='/usr/bin/chromium'):
            self.assertEqual(session.application(profile,'shortcut:'+('a'*12))[-1],'https://portal.example')
            self.assertIsNone(session.application(profile,'shortcut:unknown'))
            self.assertIsNone(session.application({**profile,'mode':'kiosk'},'shortcut:'+('a'*12)))
            profile['shortcuts'][0]['enabled']=False
            self.assertIsNone(session.application(profile,'shortcut:'+('a'*12)))

    def test_power_buttons_enforce_profile_and_use_only_fixed_actions(self):
        reply=session.subprocess.CompletedProcess([],0,stdout=b'',stderr=b'')
        profile={'approved':True,'show_shutdown':True,'show_restart':True,'confirm_power':False}
        with patch.object(session,'call',return_value=reply) as command:
            session.power_action(profile,'shutdown')
            command.assert_called_once_with(['systemctl','--no-wall','poweroff'])
            command.reset_mock();session.power_action(profile,'restart')
            command.assert_called_once_with(['systemctl','--no-wall','reboot'])
            for changes in ({'approved':False},{'mode':'kiosk'},{'show_shutdown':False}):
                command.reset_mock();session.power_action({**profile,**changes},'shutdown');command.assert_not_called()
            command.reset_mock();session.power_action(profile,'arbitrary');command.assert_not_called()
        with patch.object(session,'call',return_value=session.subprocess.CompletedProcess([],1,stdout=b'',stderr=b'')) as command:
            session.power_action({**profile,'confirm_power':True},'shutdown')
            self.assertEqual(command.call_count,1)
            self.assertEqual(command.call_args.args[0][0],'zenity')

    def test_desktop_custom_and_power_shortcuts_cleanup_preserves_other_files(self):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory);desktop=home/'Desktop';desktop.mkdir()
            (desktop/'document.txt').write_text('keep')
            reply=session.subprocess.CompletedProcess([],0,stdout=b'',stderr=b'')
            profile={'show_shutdown':True,'show_restart':True,'shortcuts':[{'id':'a'*12,'name':'Portal','url':'https://portal.example','icon':'browser','enabled':True}]}
            with patch.object(session,'stop_component',return_value=True),patch.object(session,'HOME',home),patch.object(session,'desktop_directory',return_value=desktop),patch.object(session,'call',return_value=reply):
                session.apply_desktop(profile)
                for name in ('shutdown.desktop','restart.desktop','ftc-web-'+('a'*12)+'.desktop'):
                    self.assertTrue((desktop/name).is_file())
                self.assertIn('--launch shortcut:'+('a'*12),(desktop/('ftc-web-'+('a'*12)+'.desktop')).read_text())
                session.apply_desktop({'shortcuts':[]})
                self.assertFalse((desktop/'shutdown.desktop').exists())
                self.assertFalse((desktop/'restart.desktop').exists())
                self.assertFalse((desktop/('ftc-web-'+('a'*12)+'.desktop')).exists())
                self.assertTrue((desktop/'document.txt').exists())

    def test_device_info_uses_assigned_name_and_hides_in_kiosk(self):
        self.assertEqual(device_info.caption({'device_name':'LAB-01'},'10.9.2.194'),'Máquina: LAB-01\nIP: 10.9.2.194')
        self.assertTrue(device_info.visible({}))
        self.assertFalse(device_info.visible({'mode':'kiosk'}))
        self.assertFalse(device_info.visible({'show_device_info':False}))
        with patch.object(device_info.socket,'gethostname',return_value='host-local'):
            self.assertIn('host-local',device_info.caption({},'Sem IPv4'))

    def test_device_info_ip_uses_default_route_and_refreshes(self):
        route=json.dumps([{'dev':'wifi0','metric':600},{'dev':'eth0','metric':100}])
        address=json.dumps([{'addr_info':[{'family':'inet','local':'10.9.2.194'}]}])
        replies=[device_info.subprocess.CompletedProcess([],0,stdout=route),device_info.subprocess.CompletedProcess([],0,stdout=address)]
        with patch.object(device_info.subprocess,'run',side_effect=replies) as run:
            self.assertEqual(device_info.current_ip(),'10.9.2.194')
            self.assertIn('eth0',run.call_args.args[0])
        with patch.object(device_info.subprocess,'run',side_effect=OSError):
            self.assertEqual(device_info.current_ip(),'Sem IPv4')

    def test_revision_is_retried_if_desktop_component_cannot_stop(self):
        with patch.object(session,'stop_component',return_value=False),patch.object(session,'desktop_file') as write:
            self.assertFalse(session.apply_desktop({'show_shutdown':True}))
            write.assert_not_called()
