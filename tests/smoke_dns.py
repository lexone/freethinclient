"""Verify the managed DNS snippet with a real NetworkManager in a disposable container."""
import sys
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from client import dns_config

resolver=Path('/etc/resolv.conf');original=resolver.read_bytes()
backend=Path('/etc/NetworkManager/conf.d/99-ftc-test-backend.conf')
assert not backend.exists(),'Use only a disposable Linux container'
backend.write_text('[main]\ndns=default\nrc-manager=file\n')
subprocess.run(['systemctl','start','NetworkManager'],check=True)
assert not dns_config.CONFIG.exists(),'Use only a disposable Linux container'
try:
    with tempfile.TemporaryDirectory() as temporary,patch.object(dns_config,'STATE',Path(temporary)/'status.json'):
        result=dns_config.apply({'approved':True,'dns_override':True,
            'dns_servers':['192.0.2.53','192.0.2.54'],'dns_search':['example.test']})
        assert result['state']=='applied',result
        actual=Path('/run/NetworkManager/resolv.conf').read_text()
        assert 'nameserver 192.0.2.53' in actual,actual
        assert 'nameserver 192.0.2.54' in actual,actual
        assert 'example.test' in actual,actual
        assert dns_config.apply({'approved':False})['state']=='dhcp'
        assert not dns_config.CONFIG.exists()
    print('Real NetworkManager DNS smoke passed: override, resolver generation and removal without restarting connections')
finally:
    dns_config.CONFIG.unlink(missing_ok=True)
    backend.unlink(missing_ok=True)
    for flag in ('conf','dns-rc'): subprocess.run(['nmcli','general','reload',flag],check=False)
    resolver.write_bytes(original)
