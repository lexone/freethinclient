import importlib.util
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
            with patch.object(session,'HOME',home), patch.object(session,'desktop_directory',return_value=desktop), patch.object(session,'call',return_value=reply) as command:
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
