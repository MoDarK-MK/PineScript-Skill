"""The backup, tested by actually restoring from it.

A backup nobody has restored from is a hope. These tests make one, change the
source, make another, and read the first version back out - which is the only
sequence that proves the thing works.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts"))

import backup_private


class TestBackupPrivate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name)
        # A miniature stand-in for the real repo, so the test never touches the
        # actual backup or the real indicators.
        self.source = self.work / "repo"
        (self.source / "indicators" / "demo" / "src").mkdir(parents=True)
        (self.source / "strategies").mkdir(parents=True)
        self.file = self.source / "indicators" / "demo" / "src" / "demo.pine"
        self.file.write_text("//@version=6\nindicator(\"one\")\n", encoding="utf-8")
        self.target = self.work / "backup"
        self._real_root = backup_private.ROOT
        backup_private.ROOT = self.source

    def tearDown(self):
        backup_private.ROOT = self._real_root
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(("git", "-C", str(self.target)) + args,
                              capture_output=True, text=True, check=True).stdout

    def test_a_snapshot_can_be_read_back_byte_for_byte(self):
        """Line endings are the trap here. Git normalises CRLF by default, so a
        file saved on Windows comes back subtly different unless the backup
        repository is told not to."""
        crlf = b"//@version=6\r\nindicator(\"crlf\")\r\n"
        self.file.write_bytes(crlf)
        backup_private.snapshot(self.target)
        shown = subprocess.run(
            ("git", "-C", str(self.target), "show",
             "HEAD:indicators/demo/src/demo.pine"),
            capture_output=True, check=True).stdout
        self.assertEqual(crlf, shown)

    def test_an_older_version_survives_a_later_change(self):
        """The whole point: recovering what a file USED to say."""
        backup_private.snapshot(self.target)
        first = self.git("rev-parse", "HEAD").strip()
        self.file.write_text("//@version=6\nindicator(\"two\")\n", encoding="utf-8")
        backup_private.snapshot(self.target)
        old = subprocess.run(
            ("git", "-C", str(self.target), "show",
             f"{first}:indicators/demo/src/demo.pine"),
            capture_output=True, text=True, check=True).stdout
        self.assertIn("one", old)
        self.assertNotIn("two", old)

    def test_a_deleted_file_is_still_recoverable(self):
        """The failure this exists for. Delete the source and the snapshot must
        still hold it."""
        backup_private.snapshot(self.target)
        head = self.git("rev-parse", "HEAD").strip()
        self.file.unlink()
        recovered = subprocess.run(
            ("git", "-C", str(self.target), "show",
             f"{head}:indicators/demo/src/demo.pine"),
            capture_output=True, text=True, check=True).stdout
        self.assertIn("indicator", recovered)

    def test_a_second_run_with_no_changes_commits_nothing(self):
        backup_private.snapshot(self.target)
        before = self.git("rev-list", "--count", "HEAD").strip()
        backup_private.snapshot(self.target)
        self.assertEqual(before, self.git("rev-list", "--count", "HEAD").strip())

    def test_a_file_removed_from_the_source_is_removed_from_the_snapshot(self):
        """A mirror, not an accumulation. Otherwise the backup slowly fills with
        files that were deliberately deleted."""
        extra = self.source / "indicators" / "demo" / "src" / "gone.pine"
        extra.write_text("//@version=6\n", encoding="utf-8")
        backup_private.snapshot(self.target)
        extra.unlink()
        backup_private.snapshot(self.target)
        tracked = self.git("ls-files")
        self.assertNotIn("gone.pine", tracked)
        self.assertIn("demo.pine", tracked)

    def test_it_refuses_to_back_up_into_itself(self):
        """A backup inside the thing it backs up is not a backup."""
        inside = self.source / "nested"
        code = backup_private.main(["--target", str(inside)])
        self.assertEqual(2, code)


if __name__ == "__main__":
    unittest.main()
