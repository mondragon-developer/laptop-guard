"""Distribution checks keep personal runtime data out of downloads."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools.package_release import VERSION, build_package, validate_archive


class ReleaseTests(unittest.TestCase):
    def test_windows_archive_contains_only_app_and_guide(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dist = root / "dist"
            dist.mkdir()
            (dist / "LaptopGuard.exe").write_bytes(b"test executable")
            (dist / "guard_config.json").write_text('"private phone"')
            (dist / "videos").mkdir()
            (dist / "videos" / "intruder_1.mp4").write_bytes(b"private video")
            def check(command, **kwargs):
                self.assertIn("--check", command)
                Path(command[-1]).write_text(json.dumps({"status": "ok", "version": VERSION}))
            with patch("tools.package_release.sys.platform", "win32"), \
                 patch("tools.package_release.platform.machine", return_value="AMD64"), \
                 patch("tools.package_release.subprocess.run", side_effect=check):
                archive = build_package("windows-x64", dist, root / "output")
            with zipfile.ZipFile(archive) as bundle:
                self.assertEqual({Path(name).name for name in bundle.namelist()},
                                 {"LaptopGuard.exe", "READ-ME-FIRST.txt"})
            self.assertTrue(archive.with_suffix(".zip.sha256").read_text().startswith(
                hashlib.sha256(archive.read_bytes()).hexdigest()))
            self.assertTrue((dist / "guard_config.json").exists())

    def test_rejects_private_files_in_release(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "bad.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("LaptopGuard/logs/guard.jsonl", "private")
            with self.assertRaisesRegex(ValueError, "Private runtime"):
                validate_archive(archive)
