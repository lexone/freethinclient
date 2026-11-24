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

