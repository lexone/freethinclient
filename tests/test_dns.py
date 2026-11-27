import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import fleet
from app.store import Store
from client import dns_config


class DnsTests(unittest.TestCase):
    def test_dns_inputs_accept_only_addresses_and_valid_search_domains(self):
        self.assertEqual(dns_config.servers('10.240.0.4, 10.240.0.12; 2001:db8::53'),['10.240.0.4','10.240.0.12','2001:db8::53'])
        self.assertEqual(dns_config.domains('UBEC.br, lab.ubec.br.'),['ubec.br','lab.ubec.br'])
        for value in ['dhcp','1.1.1.1\n[main]','1.1.1.1;dns=none','0.0.0.0','224.0.0.1','fe80::1%eth0',['1.1.1.1']*7]:
            with self.subTest(value=value),self.assertRaises(ValueError):dns_config.servers(value)
        for value in ['bad/name','-bad.example','good\nservers=evil','*.example']:
            with self.subTest(value=value),self.assertRaises(ValueError):dns_config.domains(value)
        with self.assertRaises(ValueError):fleet.validate_group({'name':'Lab','dns_override':True})
        with self.assertRaises(ValueError):fleet.validate_group({'name':'Lab','dns_override':'true'})
        group=fleet.validate_group({'name':'Lab','dns_override':True,'dns_servers':'10.240.0.4,10.240.0.12','dns_search':'ubec.br'})
        self.assertEqual(group['dns_servers'],['10.240.0.4','10.240.0.12'])

    def test_dns_updates_only_owned_snippet_and_reloads_without_link_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            config=Path(temporary)/'nm/90-freethinclient-dns.conf';state=Path(temporary)/'dns-status.json'
            profile={'approved':True,'dns_override':True,'dns_servers':['10.240.0.4','10.240.0.12'],'dns_search':['ubec.br','lab.ubec.br']}
            with patch.object(dns_config,'CONFIG',config),patch.object(dns_config,'STATE',state),patch.object(dns_config.subprocess,'run') as run:
                self.assertEqual(dns_config.apply(profile)['state'],'applied')
                self.assertIn('[global-dns-domain-*]\nservers=10.240.0.4,10.240.0.12',config.read_text())
                self.assertIn('searches=ubec.br,lab.ubec.br',config.read_text())
                self.assertEqual([call.args[0] for call in run.call_args_list],[['nmcli','general','reload','conf'],['nmcli','general','reload','dns-rc']])
                dns_config.apply(profile);self.assertEqual(run.call_count,2)
                self.assertEqual(dns_config.apply({'approved':False})['state'],'dhcp')
                self.assertFalse(config.exists());self.assertEqual(run.call_count,4)

    def test_dns_reload_failure_is_reported_and_retried(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(dns_config,'CONFIG',Path(temporary)/'nm/owned.conf'),patch.object(dns_config,'STATE',Path(temporary)/'state.json'),patch.object(dns_config.subprocess,'run',side_effect=OSError) as run:
                profile={'approved':True,'dns_override':True,'dns_servers':['1.1.1.1']}
                self.assertEqual(dns_config.apply(profile)['state'],'error')
                self.assertEqual(dns_config.status()['state'],'error')
                run.side_effect=None
                self.assertEqual(dns_config.apply(profile)['state'],'applied')
                self.assertEqual(run.call_count,3)

    def test_schema_migrates_and_dns_result_is_delivered_in_fleet(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=Store(temporary);fleet.initialize(store);fleet.initialize(store)
            client=fleet.enroll(store,{'mac':'02:00:00:00:00:01','name':'pc-01'})
            fleet.heartbeat(store,client['id'],{'dns_status':{'state':'applied','message':'DNS configurado'}})
            self.assertEqual(fleet.devices(store)[0]['dns_status']['message'],'DNS configurado')
            fleet.heartbeat(store,client['id'],{})
            self.assertEqual(fleet.devices(store)[0]['dns_status']['state'],'applied')
            for value in ['bad',{'state':'anything'},{'state':'error','message':'bad\ntext'}]:
                with self.subTest(value=value),self.assertRaises(ValueError):
                    fleet.heartbeat(store,client['id'],{'dns_status':value})

    def test_pxe_generators_do_not_send_dhcp_as_a_static_ip_parameter(self):
        root=Path(__file__).parents[1]
        for name in ['app/image_worker.py','scripts/setup-boot.sh']:
            self.assertNotIn(' ip=dhcp ',(root/name).read_text())
