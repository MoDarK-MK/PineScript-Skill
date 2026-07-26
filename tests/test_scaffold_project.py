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

    def test_strategy_scaffold_fills_only_skill_placeholders(self):
        """NOTE: deliberately does NOT assert `"{{" not in text` like the indicator
        test does — TradingView's own alert placeholders ({{ticker}}, {{close}},
        {{time}}) are part of the template's alert_message payloads and must
        survive scaffolding untouched."""
        with tempfile.TemporaryDirectory() as td:
            self.scaffold(td, kind="strategy", name="my_strat")
            text = (Path(td) / "my_strat" / "src" / "my_strat.pine").read_text(encoding="utf-8")
            for placeholder in ("{{TITLE}}", "{{SHORTTITLE}}", "{{OVERLAY}}"):
                self.assertNotIn(placeholder, text)
            for tv_placeholder in ("{{ticker}}", "{{close}}", "{{time}}"):
                self.assertIn(tv_placeholder, text)

    def test_strategy_template_has_all_four_risk_modules(self):
        with tempfile.TemporaryDirectory() as td:
            self.scaffold(td, kind="strategy", name="my_strat")
            text = (Path(td) / "my_strat" / "src" / "my_strat.pine").read_text(encoding="utf-8")
            for group in ("Position Sizing", "Stops & Targets",
                          "Breakeven & Trailing", "Session & Date Window"):
                self.assertIn(group, text, msg=f"missing risk module group: {group}")

    def test_scaffolded_strategy_lints_clean_in_strict_mode(self):
        with tempfile.TemporaryDirectory() as td:
            self.scaffold(td, kind="strategy", name="my_strat")
            pine = Path(td) / "my_strat" / "src" / "my_strat.pine"
            proc = run_script("pine_lint.py", pine, "--strict")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

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
