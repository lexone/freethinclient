import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from app import images, image_worker
from app.store import Store
import test_core


class ImageRulesTests(unittest.TestCase):
    def test_only_fixed_actions_and_official_citrix_urls(self):
        valid={'action':'citrix','url':'https://downloads.citrix.com/client.deb','sha256':'a'*64}
        self.assertEqual(images.validate(valid)['sha256'],'a'*64)
        for url in ('http://downloads.citrix.com/client.deb','https://evil.example/client.deb',
                    'https://downloads.citrix.com.evil.example/client.deb','https://user:pass@downloads.citrix.com/client.deb',
                    'https://downloads.citrix.com:444/client.deb','file:///tmp/client.deb','https://downloads.citrix.com/client.exe'):
            with self.subTest(url=url),self.assertRaises(ValueError): images.validate({**valid,'url':url})
        with self.assertRaises(ValueError): images.validate({**valid,'sha256':'bad'})
        with self.assertRaises(ValueError): images.validate({'action':'shell','command':'anything'})
        with self.assertRaises(ValueError): image_worker.chroot_update(Path('/unused'),'shell')

    def test_versions_only_include_installed_packages(self):
        raw='Package: chromium\nStatus: install ok installed\nVersion: 123\n\nPackage: icaclient\nStatus: deinstall ok config-files\nVersion: 99\n'
        self.assertEqual(image_worker.parse_versions(raw),{'chromium':'123'})

    def test_kernel_selection_is_numeric_and_requires_matching_initrd(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'boot').mkdir()
            for version in ('6.1.0-9-amd64','6.1.0-56-amd64'):
                (root/'boot'/('vmlinuz-'+version)).write_bytes(b'kernel')
                (root/'boot'/('initrd.img-'+version)).write_bytes(b'initrd')
            self.assertEqual(image_worker.newest_kernel(root)[0].name,'vmlinuz-6.1.0-56-amd64')
            (root/'boot/initrd.img-6.1.0-56-amd64').unlink()
            with self.assertRaises(ValueError):image_worker.newest_kernel(root)

    def test_publication_switch_and_checksum_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            boot=Path(directory).resolve();(boot/'boot.ipxe').write_text('#!ipxe\nset base http://10.9.2.175:8081\n')
            for name in image_worker.FILES:(boot/name).write_bytes(name.encode())
            (boot/'SHA256SUMS').write_text(''.join(image_worker.sha(boot/name)+'  '+name+'\n' for name in image_worker.FILES))
            with patch.object(image_worker,'BOOT',boot):
                image_worker.verify(boot)
                self.assertEqual(image_worker.source_image()[0],boot)
                target=image_worker.copy_release(boot,'a'*24)
                image_worker.activate(target,'http://10.9.2.175:8081','b'*24)
                self.assertEqual(image_worker.source_image()[0],target)
                self.assertIn('initrd=initrd.magic',(boot/'boot.ipxe').read_text())
                self.assertIn('/releases/'+('a'*24),(boot/'boot.ipxe').read_text())
                # Replace rather than overwrite the hard-linked artifact to preserve the old release.
                (target/'initrd.img').unlink();(target/'initrd.img').write_bytes(b'bad')
                with self.assertRaises(ValueError):image_worker.verify(target)
                self.assertEqual((boot/'initrd.img').read_bytes(),b'initrd.img')

    def test_vendor_redirect_cannot_escape_official_host(self):
        redirect=image_worker.VendorRedirect(('dl.google.com',))
        with self.assertRaises(ValueError):redirect.redirect_request(None,None,302,'',{},'http://dl.google.com/file')
        with self.assertRaises(ValueError):redirect.redirect_request(None,None,302,'',{},'https://evil.example/file')


class ImageApiTests(test_core.PanelTests):
    def test_admin_job_is_fixed_queued_once_and_audited(self):
        self.login()
        self.assertEqual(self.request('/api/images/jobs',{'action':'inspect'},csrf=False)[0],403)
        self.assertEqual(self.request('/api/images/jobs',{'action':'inspect'})[0],202)
        self.assertEqual(self.request('/api/images/jobs',{'action':'linux'})[0],409)
        job=json.loads((self.server.store.root/'image-jobs/request.json').read_text())
        self.assertEqual(job['action'],'inspect');self.assertEqual(job['actor'],'admin')
        self.assertTrue(self.request('/api/images')[1]['queued'])
        self.assertTrue(any('Imagem PXE: solicitado inspect' in event['action'] for event in self.server.store.events()))

    def test_operator_cannot_queue_or_read_image_jobs(self):
        self.login()
        self.request('/api/users/save',{'username':'operator','name':'Operator','password':'senha longa para operador','role':'operator'})
        code,body=self.request('/api/login',{'username':'operator','password':'senha longa para operador'})
        self.assertEqual(code,200);self.csrf=body['csrf']
        self.assertEqual(self.request('/api/images')[0],403)
        self.assertEqual(self.request('/api/images/jobs',{'action':'linux'})[0],403)
        self.assertFalse((self.server.store.root/'image-jobs/request.json').exists())

    def test_unknown_action_and_bad_vendor_input_rejected(self):
        self.login()
        self.assertEqual(self.request('/api/images/jobs',{'action':'shell'})[0],400)
        self.assertEqual(self.request('/api/images/jobs',{'action':'citrix','url':'http://127.0.0.1/evil.deb'})[0],400)
