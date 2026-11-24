import base64
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from app import updater
from app.release import extract_package, validate_package, verify_manifest
from app.security import password_hash, password_ok, version_tuple
from app.server import ControlServer, validate_profile
from app.store import Store


class CoreTests(unittest.TestCase):
    def test_password_hash(self):
        value = password_hash("senha longa para teste")
        self.assertTrue(password_ok("senha longa para teste", value))
        self.assertFalse(password_ok("errada", value))
        self.assertFalse(password_ok("errada", "invalid"))
        self.assertNotEqual(value, password_hash("senha longa para teste"))
        with self.assertRaises(ValueError):
            password_hash("curta")

    def test_numeric_versions(self):
        self.assertGreater(version_tuple("0.10.0"), version_tuple("0.9.9"))
        for invalid in ("1.0.0-rc1", "01.0.0", "v1.0.0", None, "1.0", "1.2.3/evil"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                version_tuple(invalid)

    def test_profile_validation(self):
        self.assertEqual(validate_profile({})["organization"], "Minha empresa")
        for invalid in ({"homepage": "javascript:alert(1)"}, {"citrix_url": "https://u:p@host"},
                        {"rdp_host": "host; touch /tmp/evil"}, {"organization": "a\nb"}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_profile(invalid)

    def test_store_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            store.set("profile", {"organization": "Empresa"})
            store.audit("admin", "salvo")
            self.assertEqual(Store(directory).get("profile")["organization"], "Empresa")
            self.assertEqual(store.events()[0]["action"], "salvo")


@unittest.skipUnless(shutil.which("openssl"), "OpenSSL necessário")
class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.key = self.root / "private.pem"
        self.pub = self.root / "public.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(self.key)], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(self.key), "-pubout", "-out", str(self.pub)], check=True, capture_output=True)

    def tearDown(self):
        self.directory.cleanup()

    def manifest(self):
        return {"schema": 1, "repository": "lexone/freethinclient", "version": "0.2.0", "minimum_version": "0.1.0",
                "platform": "ubuntu-24.04-amd64", "state_schema": 1,
                "asset": "freethinclint-0.2.0.tar.gz", "sha256": "a" * 64, "size": 100}

    def sign(self, manifest):
        raw = json.dumps(manifest).encode()
        file = self.root / "input.json"
        sig = self.root / "input.sig"
        file.write_bytes(raw)
        subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(self.key), "-out", str(sig), str(file)], check=True, capture_output=True)
        return raw, sig.read_bytes()

    def test_signature_valid_and_tampered(self):
        raw, sig = self.sign(self.manifest())
        parsed = verify_manifest(raw, sig, self.pub, self.root / "verify", "lexone/freethinclient")
        self.assertEqual(parsed["version"], "0.2.0")
        with self.assertRaisesRegex(ValueError, "Assinatura"):
            verify_manifest(raw.replace(b"0.2.0", b"0.3.0"), sig, self.pub, self.root / "verify", "lexone/freethinclient")

    def test_signed_wrong_repository_and_platform_rejected(self):
        for field, value in (("repository", "attacker/repo"), ("platform", "debian"), ("state_schema", 2), ("size", -1)):
            manifest = self.manifest()
            manifest[field] = value
            raw, sig = self.sign(manifest)
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_manifest(raw, sig, self.pub, self.root / "verify", "lexone/freethinclient")

    def test_checksum_and_size(self):
        path = self.root / "package"
        path.write_bytes(b"test")
        with self.assertRaisesRegex(ValueError, "Tamanho"):
            validate_package(path, {"size": 5, "sha256": "a" * 64})
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            validate_package(path, {"size": 4, "sha256": "a" * 64})

    def test_unsafe_archives_rejected(self):
        for i, (name, kind) in enumerate((("../escape", "file"), ("/absolute", "file"), ("linked", "link"), ("C:/windows", "file"), ("a\\b", "file"))):
            archive = self.root / f"bad{i}.tar.gz"
            with tarfile.open(archive, "w:gz") as output:
                item = tarfile.TarInfo(name)
                if kind == "link":
                    item.type = tarfile.SYMTYPE
                    item.linkname = "/etc"
                    output.addfile(item)
                else:
                    item.size = 1
                    output.addfile(item, io.BytesIO(b"x"))
            with self.subTest(name=name), self.assertRaises(ValueError):
                extract_package(archive, self.root / f"dest{i}", "0.2.0")
        self.assertFalse((self.root.parent / "escape").exists())

    def test_build_package_round_trip(self):
        subprocess.run([os.sys.executable, "scripts/build-release.py", "--key", str(self.key), "--output", str(self.root / "dist")], check=True, capture_output=True)
        dist = self.root / "dist"
        manifest = verify_manifest((dist / "manifest.json").read_bytes(), (dist / "manifest.sig").read_bytes(), self.pub, self.root / "checked", "lexone/freethinclient")
        package = dist / manifest["asset"]
        validate_package(package, manifest)
        extract_package(package, self.root / "extracted", manifest["version"])
        self.assertTrue((self.root / "extracted" / "web" / "index.html").exists())
        self.assertFalse(list((self.root / "extracted").rglob("*.pem")))


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        (root / "updates").mkdir()
        config = {"admin_hash": password_hash("senha longa para teste"), "repository": "lexone/freethinclient", "secure_cookie": False,
                  "update_request": str(root / "updates" / "request.json"), "update_status": str(root / "status.json")}
        self.server = ControlServer(("127.0.0.1", 0), root, config)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_port)
        self.cookie = ""
        self.csrf = ""

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.directory.cleanup()

    def request(self, path, data=None, csrf=True):
        headers = {"Cookie": self.cookie}
        if csrf:
            headers["X-CSRF-Token"] = self.csrf
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.url + path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            cookie = response.headers.get("Set-Cookie")
            if cookie:
                self.cookie = cookie.split(";", 1)[0]
            return response.status, json.loads(raw)

    def login(self):
        status, body = self.request("/api/login", {"username": "admin", "password": "senha longa para teste"})
        self.assertEqual(status, 200)
        self.csrf = body["csrf"]

    def test_authentication_and_csrf(self):
        self.assertEqual(self.request("/api/state")[0], 401)
        self.login()
        self.assertEqual(self.request("/api/state")[0], 200)
        self.assertEqual(self.request("/api/profile", {}, csrf=False)[0], 403)
        self.assertEqual(self.request("/api/profile", {"organization": "UBEC"})[0], 200)
        self.assertEqual(self.request("/api/state")[1]["profile"]["organization"], "UBEC")
        self.assertEqual(self.request("/api/logout", {})[0], 200)
        self.assertEqual(self.request("/api/state")[0], 401)

    def test_login_rate_limit(self):
        for _ in range(10):
            self.assertEqual(self.request("/api/login", {"username": "admin", "password": "errada"})[0], 401)
        self.assertEqual(self.request("/api/login", {"username": "admin", "password": "errada"})[0], 429)

    def test_update_job_and_duplicate(self):
        self.login()
        self.assertEqual(self.request("/api/update/apply", {"version": "1.2.3;evil"})[0], 400)
        self.assertEqual(self.request("/api/update/check", {})[0], 202)
        self.assertEqual(self.request("/api/update/check", {})[0], 409)
        job = json.loads(Path(self.server.configuration["update_request"]).read_text())
        self.assertEqual(job["action"], "check")

    def test_wallpaper_validation(self):
        self.login()
        self.assertEqual(self.request("/api/wallpaper", {"data": base64.b64encode(b"<svg></svg>").decode()})[0], 400)
        png = base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()
        self.assertEqual(self.request("/api/wallpaper", {"data": png})[0], 200)
        self.assertEqual(self.request("/api/state")[1]["wallpaper"]["mime"], "image/png")


class RecoveryTests(unittest.TestCase):
    def test_recovery_restores_old_code_and_database(self):
        if os.name != "posix":
            self.skipTest("Linux symlink/chown recovery test")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install, state, backups, statuses = (root / n for n in ("install", "state", "backups", "statuses"))
            for directory in (install, state, backups, statuses):
                directory.mkdir()
            previous = install / "releases" / "0.1.0"
            previous.mkdir(parents=True)
            (previous / "VERSION").write_text("0.1.0")
            current = install / "releases" / "0.2.0"
            current.mkdir()
            (current / "VERSION").write_text("0.2.0")
            (install / "current").symlink_to(current, target_is_directory=True)
            backup = backups / "fixture"
            backup.mkdir()
            (backup / "state.db").write_bytes(b"known-good")
            (state / "state.db").write_bytes(b"new-bad")
            pending = install / "pending-update.json"
            pending.write_text(json.dumps({"previous": str(previous), "backup": str(backup)}))
            with patch.multiple(updater, ROOT=install, STATE=state, BACKUPS=backups, PENDING=pending, STATUS=statuses / "status.json"), patch.object(updater, "systemctl") as service, patch.object(updater, "healthy", return_value=True), patch("shutil.chown"):
                self.assertTrue(updater.recover())
                self.assertEqual((install / "current").resolve(), previous)
                self.assertEqual((state / "state.db").read_bytes(), b"known-good")
                self.assertFalse(pending.exists())
                self.assertEqual(json.loads((statuses / "status.json").read_text())["state"], "rolled_back")
                self.assertEqual(service.call_args_list[0].args, ("stop",))


if __name__ == "__main__":
    unittest.main()
