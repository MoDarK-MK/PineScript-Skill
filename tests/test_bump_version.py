import json
import tempfile
import unittest
from pathlib import Path

from tests.helpers import run_script

import bump_version

CHANGELOG = """# Changelog — Test

## [Unreleased]
- Added a new smoothing input

## [0.1.0] - 2026-01-01
- Initial scaffold
"""


def make_project(td, version="0.1.0"):
    project = Path(td) / "proj"
    project.mkdir()
    (project / "version.json").write_text(
        json.dumps({"name": "proj", "version": version}) + "\n", encoding="utf-8")
    (project / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    return project


class TestBumpFunction(unittest.TestCase):
    def test_patch_minor_major(self):
        self.assertEqual(bump_version.bump("1.2.3", "patch"), "1.2.4")
        self.assertEqual(bump_version.bump("1.2.3", "minor"), "1.3.0")
        self.assertEqual(bump_version.bump("1.2.3", "major"), "2.0.0")

    def test_invalid_version_raises(self):
        for bad in ("1.2", "1.2.3.4", "a.b.c", "1.2.x", ""):
            with self.assertRaises(ValueError, msg=bad):
                bump_version.bump(bad, "patch")

    def test_invalid_part_raises(self):
        with self.assertRaises(ValueError):
            bump_version.bump("1.2.3", "banana")


class TestCli(unittest.TestCase):
    def test_bump_updates_version_and_changelog(self):
        with tempfile.TemporaryDirectory() as td:
            project = make_project(td)
            proc = run_script("bump_version.py", project, "--bump", "minor", "--note", "New feature")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads((project / "version.json").read_text(encoding="utf-8"))
            self.assertEqual(data["version"], "0.2.0")
            changelog = (project / "CHANGELOG.md").read_text(encoding="utf-8")
            self.assertIn("## [0.2.0]", changelog)
            # The author's own Unreleased entry is what ships. --note is only a
            # fallback for an empty section — see the dedicated tests below.
            self.assertIn("- Added a new smoothing input", changelog)
            # Fresh empty Unreleased section re-inserted at the top
            self.assertLess(changelog.index("## [Unreleased]"), changelog.index("## [0.2.0]"))

    def test_note_is_not_appended_to_an_already_written_section(self):
        """Regression: --note used to be appended under the author's own entries,
        producing a duplicate one-line summary in every release."""
        with tempfile.TemporaryDirectory() as td:
            project = make_project(td)
            proc = run_script("bump_version.py", project, "--bump", "minor",
                              "--note", "Redundant summary line")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            changelog = (project / "CHANGELOG.md").read_text(encoding="utf-8")
            self.assertIn("- Added a new smoothing input", changelog)
            self.assertNotIn("Redundant summary line", changelog)
            self.assertIn("--note was ignored", proc.stdout)

    def test_note_is_used_when_the_section_is_empty(self):
        with tempfile.TemporaryDirectory() as td:
            project = make_project(td)
            (project / "CHANGELOG.md").write_text(
                "# Changelog\n\n## [Unreleased]\n- (nothing yet)\n\n"
                "## [0.1.0] - 2026-01-01\n- Initial scaffold\n", encoding="utf-8")
            proc = run_script("bump_version.py", project, "--bump", "patch",
                              "--note", "The only note")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            changelog = (project / "CHANGELOG.md").read_text(encoding="utf-8")
            self.assertIn("- The only note", changelog)
            self.assertNotIn("--note was ignored", proc.stdout)

    def test_json_reports_whether_the_note_was_used(self):
        with tempfile.TemporaryDirectory() as td:
            project = make_project(td)
            proc = run_script("bump_version.py", project, "--bump", "patch",
                              "--note", "Ignored", "--json")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertFalse(json.loads(proc.stdout)["note_used"])

    def test_dry_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            project = make_project(td)
            before = (project / "version.json").read_text(encoding="utf-8")
            proc = run_script("bump_version.py", project, "--bump", "patch", "--dry-run")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["new_version"], "0.1.1")
            self.assertTrue(payload["dry_run"])
            self.assertEqual((project / "version.json").read_text(encoding="utf-8"), before)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as td:
            project = make_project(td)
            proc = run_script("bump_version.py", project, "--bump", "patch", "--json")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["old_version"], "0.1.0")
            self.assertEqual(payload["new_version"], "0.1.1")
            self.assertFalse(payload["dry_run"])
            self.assertEqual(len(payload["updated_files"]), 2)

    def test_invalid_version_string_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as td:
            project = make_project(td, version="not-a-version")
            proc = run_script("bump_version.py", project, "--bump", "patch")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("Invalid version string", proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)

    def test_missing_version_json_fails(self):
        with tempfile.TemporaryDirectory() as td:
            proc = run_script("bump_version.py", td, "--bump", "patch")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("not found", proc.stderr)


if __name__ == "__main__":
    unittest.main()
