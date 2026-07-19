import tempfile
import unittest
from pathlib import Path

from tests.helpers import run_script


def scaffold(td, kind="indicator", name="rel_test"):
    proc = run_script("scaffold_project.py", "--kind", kind, "--name", name, "--out", td)
    assert proc.returncode == 0, proc.stderr
    return Path(td) / name


class TestReleaseBundle(unittest.TestCase):
    def test_bundle_from_scaffolded_indicator(self):
        with tempfile.TemporaryDirectory() as td:
            project = scaffold(td)
            proc = run_script("generate_release_bundle.py", project)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            release = project / "release"
            self.assertTrue((release / "rel_test.pine").exists())
            self.assertTrue((release / "PUBLISH_DESCRIPTION.md").exists())
            summary = (release / "RELEASE_SUMMARY.txt").read_text(encoding="utf-8")
            self.assertIn("READY TO PUBLISH.", summary)

    def test_test_mode_default_true_blocks_release(self):
        with tempfile.TemporaryDirectory() as td:
            project = scaffold(td)
            pine = project / "src" / "rel_test.pine"
            text = pine.read_text(encoding="utf-8")
            text += '\nbool testModeInput = input.bool(true, "Test Mode", group="Debug")\n'
            pine.write_text(text, encoding="utf-8")
            proc = run_script("generate_release_bundle.py", project)
            self.assertEqual(proc.returncode, 1)
            summary = (project / "release" / "RELEASE_SUMMARY.txt").read_text(encoding="utf-8")
            self.assertIn("NOT READY", summary)
            self.assertIn("testModeInput", summary)

    def test_missing_project_dir_fails(self):
        proc = run_script("generate_release_bundle.py", "no_such_project_dir")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("does not exist", proc.stderr)

    def test_strategy_description_includes_backtest_disclosure(self):
        with tempfile.TemporaryDirectory() as td:
            project = scaffold(td, kind="strategy", name="rel_strat")
            run_script("generate_release_bundle.py", project)
            desc = (project / "release" / "PUBLISH_DESCRIPTION.md").read_text(encoding="utf-8")
            self.assertIn("Backtest settings disclosure", desc)


if __name__ == "__main__":
    unittest.main()
