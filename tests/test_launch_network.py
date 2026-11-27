import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from app import fleet
from client import session,network
from client.launch_options import arguments,rdp_host


class LaunchAndNetworkTests(unittest.TestCase):
    def test_app_modes_and_extra_parameters_survive_group_validation(self):
        profile=fleet.validate_group({'name':'Lab','mode':'rdp','rdp_prompt_server':True,
            'browser_window_mode':'kiosk','browser_arguments':'--incognito --window-size=1280,800',
            'rdp_window_mode':'window','rdp_arguments':'+clipboard /size:1440x900',
            'allow_network_settings':True})
        self.assertTrue(profile['allow_network_settings'])
        self.assertEqual(profile['rdp_window_mode'],'window')
        for changed in ({'rdp_window_mode':'command'},{'allow_network_settings':'yes'},
                        {'browser_arguments':'--no-sandbox'},{'rdp_arguments':'/cert:ignore'},
                        {'rdp_arguments':'/p:secret'},{'browser_autostart':'yes'},
                        {'citrix_autostart':True},{'rdp_autostart':True,'rdp_prompt_server':False}):
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                fleet.validate_group({'name':'Lab',**changed})

    def test_arguments_cannot_replace_executable_or_inject_sensitive_flags(self):
        self.assertEqual(arguments('--proxy-server="http://proxy.example:8080" --proxy-bypass-list="*.local;<local>"','browser'),
            ['--proxy-server=http://proxy.example:8080','--proxy-bypass-list=*.local;<local>'])
        for app,value in [('browser','--user-data-dir=/root'),('browser','--remote-debugging-port=9222'),
                          ('browser','--load-extension=/tmp/evil'),('browser','--ignore-certificate-errors'),
                          ('browser','--proxy-server=http://u:p@proxy:8080'),('browser','--incognito; touch /tmp/pwn'),
                          ('browser','"unclosed'),('rdp','/v:other'),('rdp','/drive:root,/'),('rdp','/u:user')]:
            with self.subTest(value=value),self.assertRaises(ValueError): arguments(value,app)
        for value in ['host.example','10.9.2.2:3389','[::1]:3389']: self.assertTrue(rdp_host(value))
        for value in ['-evil','host;cmd','/cert:ignore']: self.assertFalse(rdp_host(value))

    def test_individual_modes_take_precedence_and_shortcuts_use_separate_browser_profiles(self):
        profile={'homepage':'https://example.org','fullscreen':True,'browser_window_mode':'window',
                 'browser_arguments':'--disable-gpu','rdp_host':'rdp.example','rdp_window_mode':'window',
                 'rdp_arguments':'+clipboard /size:1440x900',
                 'shortcuts':[{'id':'a'*12,'url':'https://portal.example','window_mode':'kiosk','arguments':'--incognito'}]}
        with patch.object(session.shutil,'which',return_value='/usr/bin/chromium'):
            browser=session.application(profile,'browser')
            self.assertNotIn('--start-fullscreen',browser)
            self.assertIn('--disable-gpu',browser)
            shortcut=session.application(profile,'shortcut:'+('a'*12))
            self.assertIn('--kiosk',shortcut)
            self.assertEqual(shortcut[-1],'https://portal.example')
            self.assertNotEqual(next(a for a in browser if a.startswith('--user-data-dir=')),
                                next(a for a in shortcut if a.startswith('--user-data-dir=')))
        rdp=session.application(profile,'rdp')
        self.assertNotIn('/f',rdp);self.assertIn('/size:1440x900',rdp)
        self.assertIn('/cert:deny',rdp)
        self.assertIn('/f',session.application({**profile,'kiosk_app':'rdp'},'kiosk'))

    def test_desktop_can_autostart_multiple_apps_but_group_kiosk_only_one(self):
        profile={'mode':'desktop','browser_autostart':True,'rdp_autostart':True,
                 'shortcuts':[{'id':'a'*12,'autostart':True},{'id':'b'*12,'autostart':True,'enabled':False}]}
        self.assertEqual(session.startup_applications(profile),['browser','rdp','shortcut:'+('a'*12)])
        self.assertEqual(session.startup_applications({**profile,'mode':'kiosk'}),['kiosk'])
        self.assertEqual(session.startup_applications({**profile,'mode':'rdp'}),['rdp'])

    def test_prompted_rdp_destination_is_validated_and_password_stays_on_stdin(self):
        child=Mock();child.stdin=io.BytesIO();child.stdin.close=Mock()
        dialog=Mock(returncode=0,stdout=b'rdp.example:3389\nuser\nsecret\n')
        with patch.object(session.subprocess,'run',return_value=dialog),patch.object(session.subprocess,'Popen',return_value=child) as spawn:
            self.assertIs(session.launch({'rdp_prompt_server':True},'rdp'),child)
            argv=spawn.call_args.args[0]
            self.assertIn('/v:rdp.example:3389',argv)
            self.assertNotIn('secret',' '.join(argv))
            self.assertEqual(child.stdin.getvalue(),b'secret\n')
        dialog.stdout=b'-evil\nuser\nsecret\n'
        with patch.object(session.subprocess,'run',return_value=dialog),patch.object(session,'call'),patch.object(session.subprocess,'Popen') as spawn:
            self.assertIsNone(session.launch({'rdp_prompt_server':True},'rdp'));spawn.assert_not_called()

    def test_network_controls_require_current_approved_profile(self):
        for profile in ({},{'approved':True},{'approved':False,'allow_network_settings':True}):
            with patch.object(network,'read_profile',return_value=profile),patch.object(network.subprocess,'Popen') as spawn:
                network.open_tool('wifi');spawn.assert_not_called()
        with patch.object(network,'read_profile',return_value={'approved':True,'allow_network_settings':True}),patch.object(network.subprocess,'Popen') as spawn:
            network.open_tool('wifi')
            self.assertIn('nmtui-connect',spawn.call_args.args[0])
            network.open_tool('shell');self.assertEqual(spawn.call_count,1)

    def test_network_launcher_is_created_and_removed_with_group_permission(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)
            reply=session.subprocess.CompletedProcess([],0,stdout=b'',stderr=b'')
            with patch.object(session,'HOME',home),patch.object(session,'desktop_directory',return_value=home/'Desktop'),patch.object(session,'stop_component',return_value=True),patch.object(session,'call',return_value=reply):
                session.apply_desktop({'approved':True,'allow_network_settings':True,'rdp_prompt_server':True})
                self.assertTrue((home/'Desktop/network.desktop').exists())
                self.assertTrue((home/'Desktop/remote.desktop').exists())
                session.apply_desktop({'approved':True,'allow_network_settings':False})
                self.assertFalse((home/'Desktop/network.desktop').exists())

    def test_shortcut_opening_options_are_validated(self):
        item={'id':'a'*12,'name':'Portal','url':'https://portal.example',
              'window_mode':'fullscreen','arguments':'--incognito','autostart':True}
        saved=fleet.validate_group({'name':'Lab','shortcuts':[item]})['shortcuts'][0]
        self.assertEqual(saved['window_mode'],'fullscreen');self.assertTrue(saved['autostart'])
        for change in ({'arguments':'--no-sandbox'},{'autostart':'yes'},{'window_mode':'shell'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                fleet.validate_group({'name':'Lab','shortcuts':[{**item,**change}]})

    def test_diagnostic_does_not_expose_saved_wifi_secrets_or_change_network(self):
        with patch.object(network,'output',return_value='fixture') as command,patch.object(network,'read_profile',return_value={'homepage':'https://portal.example'}),patch.object(network.socket,'getaddrinfo',side_effect=OSError('DNS failed')):
            text=network.diagnostics()
        self.assertIn('Falha de DNS',text)
        args=[call.args[0] for call in command.call_args_list]
        self.assertFalse(any('--show-secrets' in call or 'modify' in call or 'connect' in call for call in args))
        self.assertTrue(any(call[:2]==['ip','route'] for call in args))
