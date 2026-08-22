import tempfile
import unittest
from pathlib import Path

from tests.helpers import run_script

from generate_release_bundle import check_test_mode_default


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


def patch_source(project, name, old, new):
    pine = project / "src" / f"{name}.pine"
    text = pine.read_text(encoding="utf-8")
    assert old in text, f"pattern not found in template: {old!r}"
    pine.write_text(text.replace(old, new), encoding="utf-8")
    return pine


class TestStrategyRealismChecks(unittest.TestCase):
    def summary(self, project):
        return (project / "release" / "RELEASE_SUMMARY.txt").read_text(encoding="utf-8")

    def test_clean_strategy_passes_realism_checks(self):
        with tempfile.TemporaryDirectory() as td:
            project = scaffold(td, kind="strategy", name="rel_strat")
            proc = run_script("generate_release_bundle.py", project)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("Strategy realism checks: none found. OK.", self.summary(project))
            self.assertIn("READY TO PUBLISH.", self.summary(project))

    def test_zero_cost_backtest_blocks_release(self):
        with tempfile.TemporaryDirectory() as td:
            project = scaffold(td, kind="strategy", name="rel_strat")
            patch_source(project, "rel_strat",
                         "commission_value=0.05,\n     slippage=1,",
                         "commission_value=0,\n     slippage=0,")
            proc = run_script("generate_release_bundle.py", project)
            self.assertEqual(proc.returncode, 1)
            summary = self.summary(project)
            self.assertIn("BLOCKING:", summary)
            self.assertIn("frictionless backtest", summary)
            self.assertIn("NOT READY", summary)

    def test_lookahead_on_without_offset_blocks_release(self):
        with tempfile.TemporaryDirectory() as td:
            project = scaffold(td, kind="strategy", name="rel_strat")
            pine = project / "src" / "rel_strat.pine"
            pine.write_text(
                pine.read_text(encoding="utf-8") +
                '\nfloat peek = request.security(syminfo.tickerid, "D", close, '
                'lookahead=barmerge.lookahead_on)\nplot(peek, "Peek")\n',
                encoding="utf-8")
            proc = run_script("generate_release_bundle.py", project)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("lookahead bias", self.summary(project))

    def test_lookahead_on_with_offset_is_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            project = scaffold(td, kind="strategy", name="rel_strat")
            pine = project / "src" / "rel_strat.pine"
            pine.write_text(
                pine.read_text(encoding="utf-8") +
                '\nfloat prevDayHigh = request.security(syminfo.tickerid, "D", high[1], '
                'lookahead=barmerge.lookahead_on)\nplot(prevDayHigh, "PDH")\n',
                encoding="utf-8")
            proc = run_script("generate_release_bundle.py", project)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("READY TO PUBLISH.", self.summary(project))

    def test_heikin_ashi_ticker_blocks_release(self):
        with tempfile.TemporaryDirectory() as td:
            project = scaffold(td, kind="strategy", name="rel_strat")
            pine = project / "src" / "rel_strat.pine"
            pine.write_text(
                pine.read_text(encoding="utf-8") +
                '\nfloat haClose = request.security(ticker.heikinashi(syminfo.tickerid), '
                'timeframe.period, close)\nplot(haClose, "HA")\n',
                encoding="utf-8")
            proc = run_script("generate_release_bundle.py", project)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("synthetic prices", self.summary(project))

    def test_oversized_default_qty_is_advisory_not_blocking(self):
        with tempfile.TemporaryDirectory() as td:
            project = scaffold(td, kind="strategy", name="rel_strat")
            patch_source(project, "rel_strat", "default_qty_value=10,", "default_qty_value=90,")
            proc = run_script("generate_release_bundle.py", project)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            summary = self.summary(project)
            self.assertIn("NOTE:", summary)
            self.assertIn("sustainable-sizing", summary)
            self.assertIn("READY TO PUBLISH.", summary)

    def test_advisory_blocks_in_strict_mode(self):
        with tempfile.TemporaryDirectory() as td:
            project = scaffold(td, kind="strategy", name="rel_strat")
            patch_source(project, "rel_strat", "default_qty_value=10,", "default_qty_value=90,")
            proc = run_script("generate_release_bundle.py", project, "--strict")
            self.assertEqual(proc.returncode, 1)

    def test_description_prefills_real_backtest_numbers(self):
        with tempfile.TemporaryDirectory() as td:
            project = scaffold(td, kind="strategy", name="rel_strat")
            run_script("generate_release_bundle.py", project)
            desc = (project / "release" / "PUBLISH_DESCRIPTION.md").read_text(encoding="utf-8")
            self.assertIn("Initial capital: 10000 USD", desc)
            self.assertIn("Commission: 0.05% per trade", desc)
            self.assertIn("Slippage: 1 tick(s)", desc)

    def test_indicator_gets_no_strategy_realism_block(self):
        with tempfile.TemporaryDirectory() as td:
            project = scaffold(td, kind="indicator", name="rel_ind")
            run_script("generate_release_bundle.py", project)
            self.assertNotIn("Strategy realism checks",
                             (project / "release" / "RELEASE_SUMMARY.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()


class TestDebugToggleHeuristic(unittest.TestCase):
    """The gate must catch real debug toggles and nothing else.

    Substring matching flagged `preferUntestedInput` because "Untested"
    contains "test", blocking a release that was fine. A gate with false
    positives is a gate somebody turns off, so the negative cases here matter
    as much as the positive ones.
    """

    def flagged(self, name):
        return bool(check_test_mode_default(
            f'bool {name} = input.bool(true, "X", group="G")'))

    def test_real_debug_toggles_are_caught(self):
        for name in ("testModeInput", "showTestInput", "test_mode",
                     "testingInput", "debugPanelInput", "DEBUG_MODE"):
            with self.subTest(name=name):
                self.assertTrue(self.flagged(name))

    def test_words_merely_containing_test_are_not(self):
        for name in ("preferUntestedInput", "latestOnlyInput",
                     "untestedOnlyInput", "showTableInput", "contestInput"):
            with self.subTest(name=name):
                self.assertFalse(self.flagged(name))

    def test_false_default_is_never_flagged(self):
        self.assertEqual([], check_test_mode_default(
            'bool testModeInput = input.bool(false, "Test Mode")'))
