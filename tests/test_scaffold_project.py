import json
import tempfile
import unittest
from pathlib import Path

from tests.helpers import run_script


class TestScaffold(unittest.TestCase):
    def scaffold(self, td, kind="indicator", name="my_test_ind", extra=()):
        return run_script(
            "scaffold_project.py", "--kind", kind, "--name", name, "--out", td, *extra)

    def test_creates_standard_layout(self):
        with tempfile.TemporaryDirectory() as td:
            proc = self.scaffold(td)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            project = Path(td) / "my_test_ind"
            pine = project / "src" / "my_test_ind.pine"
            self.assertTrue(pine.exists())
            self.assertTrue((project / "CHANGELOG.md").exists())
            data = json.loads((project / "version.json").read_text(encoding="utf-8"))
            self.assertEqual(data["version"], "0.1.0")
            self.assertEqual(data["kind"], "indicator")
            text = pine.read_text(encoding="utf-8")
            self.assertIn("My Test Ind", text)      # {{TITLE}} filled from slug
            self.assertNotIn("{{", text)            # no unfilled placeholders

    def test_strategy_kind_uses_strategy_template(self):
        with tempfile.TemporaryDirectory() as td:
            proc = self.scaffold(td, kind="strategy", name="my_strat")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = (Path(td) / "my_strat" / "src" / "my_strat.pine").read_text(encoding="utf-8")
            self.assertIn("strategy(", text)

    def test_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(self.scaffold(td).returncode, 0)
            proc = self.scaffold(td)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("refusing to overwrite", proc.stdout + proc.stderr)

    def test_scaffolded_indicator_lints_clean_of_errors(self):
        with tempfile.TemporaryDirectory() as td:
            self.scaffold(td)
            pine = Path(td) / "my_test_ind" / "src" / "my_test_ind.pine"
            proc = run_script("pine_lint.py", pine)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
