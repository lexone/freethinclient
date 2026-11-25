"""Disposable image publish/rollback test; package installation is mocked explicitly."""
import json
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import image_worker as worker


def fixture(root,boot):
    for name in ('etc','boot','var/lib/dpkg','usr/local/lib/freethinclient'):
        (root/name).mkdir(parents=True,exist_ok=True)
    (root/'etc/debian_version').write_text('12.12')
    (root/'var/lib/dpkg/status').write_text('Package: chromium\nStatus: install ok installed\nVersion: fixture-1\n')
    (root/'boot/vmlinuz-6.1.0-56-amd64').write_bytes(b'kernel-fixture')
    (root/'boot/initrd.img-6.1.0-56-amd64').write_bytes(b'initrd-fixture')
    boot.mkdir(parents=True,exist_ok=True)
    (boot/'vmlinuz').write_bytes(b'kernel-fixture');(boot/'initrd.img').write_bytes(b'initrd-fixture')
    subprocess.run(['mksquashfs',str(root),str(boot/'filesystem.squashfs'),'-noappend','-comp','xz',
                    '-p','dev d 755 0 0','-p','dev/null c 666 0 0 1 3','-p','dev/console c 600 0 0 5 1'],check=True)
    (boot/'SHA256SUMS').write_text(''.join(worker.sha(boot/name)+'  '+name+'\n' for name in worker.FILES))
    (boot/'boot.ipxe').write_text('#!ipxe\nset base http://10.9.2.175:8081\n')


def main():
    if '--credentials-test' in sys.argv:
        import os
        # Run in a disposable process: exercise APT's temporary and final UID/GID drops.
        os.setegid(65534)
        os.seteuid(42)
        assert os.geteuid()==42
        os.seteuid(0)
        os.setegid(0)
        os.setgroups([])
        os.setresgid(65534,65534,65534)
        os.setresuid(42,42,42)
        assert os.getresuid()==(42,42,42)
        print('APT credential switching passed under image service restrictions')
        return
    if '--extract-test' in sys.argv:
        import os,stat
        workspace=Path('/var/lib/freethinclient-image')
        try:
            os.mknod(workspace/'mknod-probe',stat.S_IFCHR|0o600,os.makedev(1,3))
        except PermissionError:
            pass
        else:
            raise AssertionError('The regression test must run without device creation privileges')
        target=workspace/'device-extraction-test'
        worker.extract_image(Path('/srv/freethinclient/boot/filesystem.squashfs'),target,workspace/'device-extraction.log')
        assert (target/'dev').is_dir()
        assert not list((target/'dev').iterdir()),'Archived device nodes must be excluded'
        assert (target/'etc/debian_version').read_text()=='12.12'
        print('Device-node extraction passed with PrivateDevices=yes; all ordinary errors remain fatal')
        return
    with tempfile.TemporaryDirectory() as temporary:
        base=Path(temporary);boot=base/'boot';work=base/'work';work.mkdir()
        fixture(base/'root',boot)
        if '--service' in sys.argv:
            published=Path('/srv/freethinclient/boot')
            for name in (*worker.FILES,'SHA256SUMS','boot.ipxe'):
                (published/name).write_bytes((boot/name).read_bytes())
            request=Path('/var/lib/freethinclient/image-jobs/request.json')
            request.write_text(json.dumps({'action':'inspect','id':secrets.token_hex(12),'actor':'admin'}))
            subprocess.run(['systemctl','start','freethinclient-image.service'],check=True)
            status=json.loads(Path('/var/lib/freethinclient-image/status.json').read_text())
            assert status['state']=='done',status
            assert status['versions']['chromium']=='fixture-1',status
            assert not request.exists()
            subprocess.run(['systemd-run','--unit=ftc-device-extraction-test','--wait','--pipe',
                '--property=PrivateDevices=yes','--property=PrivateTmp=yes','--property=ProtectSystem=strict',
                '--property=ReadWritePaths=/var/lib/freethinclient-image',
                'python3','/source/tests/smoke_image_portal.py','--extract-test'],check=True)
            # Copy the deployed worker's sandbox settings to the credential probe.
            unit=Path('/etc/systemd/system/freethinclient-image.service').read_text()
            keys={'User','AmbientCapabilities','NoNewPrivileges','PrivateTmp','PrivateDevices',
                  'PrivateMounts','ProtectSystem','ProtectHome','ProtectKernelTunables',
                  'ProtectKernelModules','ProtectControlGroups'}
            properties=[]
            for line in unit.splitlines():
                if line.partition('=')[0] in keys:
                    properties+=['--property='+line]
            subprocess.run(['systemd-run','--unit=ftc-apt-credentials-test','--wait','--pipe',
                *properties,'unshare','--mount','--fork','python3',
                '/source/tests/smoke_image_portal.py','--credentials-test'],check=True)
            print('Image service smoke passed under its systemd restrictions')
            return
        original=worker.run_command;namespace_calls=[]
        def commands(args,log,timeout=1800):
            if args[0]=='unshare':
                namespace_calls.append(args)
                return  # A tiny fixture cannot run apt/update-initramfs; these are not exercised here.
            return original(args,log,timeout)
        with patch.object(worker,'BOOT',boot),patch.object(worker,'WORK',work),patch.object(worker,'run_command',side_effect=commands):
            events=[]
            result=worker.perform({'action':'client','id':'a'*24},lambda *a,**k:events.append(a),work/'job.log')
            assert result['rollback_available']
            current,origin,previous=worker.source_image()
            assert current.name=='a'*24
            assert (current/'vmlinuz').read_bytes()==b'kernel-fixture'
            assert namespace_calls and namespace_calls[0][-1]=='client'
            content=subprocess.check_output(['unsquashfs','-cat',str(current/'filesystem.squashfs'),'usr/share/freethinclient/boot-banner.txt']).decode()
            assert 'Everton S Oliveira' in content and 'FREETHINCLIENT' in content
            script=subprocess.check_output(['unsquashfs','-cat',str(current/'filesystem.squashfs'),'usr/local/lib/freethinclient/session.py']).decode()
            assert 'metadata::xfce-exe-checksum' in script
            info=subprocess.check_output(['unsquashfs','-cat',str(current/'filesystem.squashfs'),'etc/xdg/autostart/freethinclient-info.desktop']).decode()
            assert 'device_info.py' in info
            result=worker.perform({'action':'rollback','id':'b'*24},lambda *a,**k:None,work/'job.log')
            assert worker.source_image()[0].name==previous
            assert result['versions']['chromium']=='fixture-1'
            assert (boot/'releases'/('a'*24)/'filesystem.squashfs').is_file()
        print('Image portal smoke passed: real SquashFS, assets, banner, publication and rollback; package update mocked')


if __name__=='__main__': main()
