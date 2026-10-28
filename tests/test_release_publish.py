import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.ensure_release import ensure_release


class PublishTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.assets = []
        for target in ("windows-x64", "macos-apple-silicon", "macos-intel"):
            name = f"LaptopGuard-1.1.0-{target}.zip"
            data = b"test artifact"
            (self.folder / name).write_bytes(data)
            (self.folder / (name + ".sha256")).write_text(hashlib.sha256(data).hexdigest() + "  " + name)
            self.assets.extend({"name": name + suffix, "state": "uploaded", "size": 10}
                               for suffix in ("", ".sha256"))

    def call(self):
        return ensure_release("owner/repo", "v1.1.0", self.folder, "notes.md")

    def release(self, draft=False):
        return {"tag_name": "v1.1.0", "draft": draft, "assets": self.assets,
                "html_url": "draft" if draft else "public"}

    def response(self, pages):
        return subprocess.CompletedProcess([], 0, stdout=json.dumps(pages))

    def test_published_release_is_preserved_without_mutation(self):
        with patch("tools.ensure_release.subprocess.run", return_value=self.response([[self.release()]])) as run:
            self.assertEqual(self.call(), "public")
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][1], "api")

    def test_draft_release_is_preserved_without_duplicate(self):
        with patch("tools.ensure_release.subprocess.run", return_value=self.response([[self.release(True)]])) as run:
            self.assertEqual(self.call(), "draft")
        self.assertEqual(run.call_count, 1)

    def test_published_release_wins_over_duplicate_draft_across_pages(self):
        draft = self.release(True)
        draft["assets"] = []
        with patch("tools.ensure_release.subprocess.run", return_value=self.response([[draft], [self.release()]])) as run:
            self.assertEqual(self.call(), "public")
        self.assertEqual(run.call_count, 1)

    def test_missing_release_creates_only_a_draft(self):
        with patch("tools.ensure_release.subprocess.run", side_effect=[self.response([[]]),
                   subprocess.CompletedProcess([], 0, stdout="new draft\n")]) as run:
            self.assertEqual(self.call(), "new draft")
        command = run.call_args.args[0]
        self.assertEqual(command[:4], ["gh", "release", "create", "v1.1.0"])
        self.assertIn("--verify-tag", command)
        self.assertIn("--draft", command)
        self.assertNotIn("--clobber", command)

    def test_api_failure_never_creates_a_release(self):
        with patch("tools.ensure_release.subprocess.run", side_effect=subprocess.CalledProcessError(1, "gh")) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                self.call()
        self.assertEqual(run.call_count, 1)

    def test_incomplete_existing_release_fails_without_overwriting(self):
        incomplete = self.release()
        incomplete["assets"] = []
        with patch("tools.ensure_release.subprocess.run", return_value=self.response([[incomplete]])) as run:
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                self.call()
        self.assertEqual(run.call_count, 1)

    def test_corrupt_artifact_never_calls_github(self):
        next(self.folder.glob("*.zip")).write_bytes(b"corrupt")
        with patch("tools.ensure_release.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
                self.call()
        run.assert_not_called()
