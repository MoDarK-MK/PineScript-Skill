import json
import tempfile
import unittest
from pathlib import Path

from tests.helpers import REPO_ROOT, VALID_INDICATOR, VALID_STRATEGY, run_script

import pine_lint


def lint_text(text):
    """Lint a Pine source string with the default config; returns LintResult."""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "script.pine"
        path.write_text(text, encoding="utf-8")
        return pine_lint.lint_file(str(path), dict(pine_lint.DEFAULT_CONFIG))


def codes(result):
    return {f.code for f in result.findings}


class TestRuleCatalog(unittest.TestCase):
    def test_has_34_rules_and_no_pine024(self):
        self.assertEqual(len(pine_lint.RULES), 34)
        self.assertNotIn("PINE024", pine_lint.RULES)
        self.assertIn("PINE001", pine_lint.RULES)
        self.assertIn("PINE035", pine_lint.RULES)

    def test_list_rules_cli(self):
        proc = run_script("pine_lint.py", "--list-rules")
        self.assertEqual(proc.returncode, 0)
        lines = [l for l in proc.stdout.splitlines() if l.strip()]
        self.assertEqual(len(lines), 34)


class TestCoreRules(unittest.TestCase):
    def test_valid_indicator_is_clean(self):
        result = lint_text(VALID_INDICATOR)
        self.assertEqual([], result.by_severity("error"),
                         msg=[f.msg for f in result.findings])
        self.assertTrue(result.ok())

    def test_missing_version_pragma(self):
        result = lint_text('indicator("X", overlay=true)\nplot(close)\n')
        self.assertIn("PINE001", codes(result))
        self.assertFalse(result.ok())

    def test_missing_declaration(self):
        result = lint_text("//@version=6\nplot(close)\n")
        self.assertIn("PINE002", codes(result))

    def test_deprecated_study(self):
        result = lint_text('//@version=6\nstudy("X")\nplot(close)\n')
        self.assertIn("PINE004", codes(result))

    def test_transp_removed(self):
        text = VALID_INDICATOR + "bgcolor(color.red, transp=80)\n"
        self.assertIn("PINE011", codes(lint_text(text)))

    def test_when_removed(self):
        text = (
            '//@version=6\nstrategy("S", overlay=true, default_qty_type=strategy.percent_of_equity, '
            "default_qty_value=10, commission_type=strategy.commission.percent, commission_value=0.1)\n"
            'strategy.entry("L", strategy.long, when=close > open)\n'
        )
        self.assertIn("PINE010", codes(lint_text(text)))

    def test_missing_overlay_warns(self):
        result = lint_text('//@version=6\nindicator("X")\nplot(close)\n')
        self.assertIn("PINE022", codes(result))
        # warning only — still ok() in non-strict mode, fails in strict
        self.assertTrue(result.ok())
        self.assertFalse(result.ok(strict=True))

    def test_unbalanced_parens(self):
        result = lint_text(VALID_INDICATOR + "x = math.max(1, 2\n")
        self.assertIn("PINE003", codes(result))

    def test_switch_arm_with_string_value_not_flagged_as_empty_block(self):
        # Regression: `3 => "★★★"` used to strip to `3 =>` and trip PINE020.
        text = VALID_INDICATOR + (
            'starString(int score) =>\n'
            '    switch score\n'
            '        3 => "***"\n'
            '        2 => "**"\n'
            '        => "-"\n'
            'plotchar(close, "S", "", location.top)\n'
        )
        self.assertNotIn("PINE020", codes(lint_text(text)))

    def test_no_output_call(self):
        result = lint_text('//@version=6\nindicator("X", overlay=true)\nx = close\n')
        self.assertIn("PINE027", codes(result))


class TestSuppressions(unittest.TestCase):
    LONG_LINE = "x = 1  " + "// " + "z" * 130

    def test_finding_without_suppression(self):
        self.assertIn("PINE008", codes(lint_text(VALID_INDICATOR + self.LONG_LINE + "\n")))

    def test_disable_next_line(self):
        text = VALID_INDICATOR + "// pine-lint-disable-next-line PINE008\n" + self.LONG_LINE + "\n"
        self.assertNotIn("PINE008", codes(lint_text(text)))

    def test_disable_file_wide(self):
        text = "// pine-lint-disable PINE008\n" + VALID_INDICATOR + self.LONG_LINE + "\n"
        self.assertNotIn("PINE008", codes(lint_text(text)))


class TestStrategyRules(unittest.TestCase):
    def test_valid_strategy_is_completely_clean(self):
        result = lint_text(VALID_STRATEGY)
        self.assertEqual([], result.findings, msg=[f"{f.code}: {f.msg}" for f in result.findings])

    def test_strategy_template_is_fully_clean(self):
        """The shipped template must stay at 0/0/0, not merely 0 errors."""
        path = REPO_ROOT / "assets" / "templates" / "strategy_template.pine"
        result = pine_lint.lint_file(str(path), dict(pine_lint.DEFAULT_CONFIG))
        self.assertEqual([], result.findings, msg=[f"{f.code}: {f.msg}" for f in result.findings])

    # PINE021 — declaration completeness
    def test_pine021_requires_initial_capital_and_slippage(self):
        text = VALID_STRATEGY.replace("initial_capital=10000, ", "").replace(", slippage=1", "")
        result = lint_text(text)
        self.assertIn("PINE021", codes(result))
        self.assertNotIn("PINE021", codes(lint_text(VALID_STRATEGY)))

    def test_pine021_ignores_parameter_named_only_in_a_comment(self):
        text = VALID_STRATEGY.replace(
            "initial_capital=10000, ", "").replace(
            ", slippage=1", "") + "\n// initial_capital and slippage are left at defaults\n"
        self.assertIn("PINE021", codes(lint_text(text)))

    # PINE029 — exit with no level
    def test_pine029_exit_without_any_level(self):
        text = VALID_STRATEGY.replace(
            'strategy.exit("Long Exit", "Long", stop=avgPrice * 0.98, limit=avgPrice * 1.04)',
            'strategy.exit("Long Exit", "Long")')
        self.assertIn("PINE029", codes(lint_text(text)))
        self.assertNotIn("PINE029", codes(lint_text(VALID_STRATEGY)))

    # PINE030 — relative + absolute of the same type
    def test_pine030_mixes_relative_and_absolute(self):
        text = VALID_STRATEGY.replace(
            "stop=avgPrice * 0.98, limit=avgPrice * 1.04",
            "stop=avgPrice * 0.98, loss=20")
        self.assertIn("PINE030", codes(lint_text(text)))
        self.assertNotIn("PINE030", codes(lint_text(VALID_STRATEGY)))

    # PINE031 — tick parameter given a price expression
    def test_pine031_price_expression_in_tick_param(self):
        text = VALID_STRATEGY.replace(
            "stop=avgPrice * 0.98, limit=avgPrice * 1.04",
            "trail_price=avgPrice * 1.02, trail_offset=avgPrice * 0.01")
        self.assertIn("PINE031", codes(lint_text(text)))

    def test_pine031_accepts_mintick_conversion_and_literals(self):
        converted = VALID_STRATEGY.replace(
            "stop=avgPrice * 0.98, limit=avgPrice * 1.04",
            "trail_price=avgPrice * 1.02, trail_offset=int(avgPrice * 0.01 / syminfo.mintick)")
        self.assertNotIn("PINE031", codes(lint_text(converted)))
        literal = VALID_STRATEGY.replace(
            "stop=avgPrice * 0.98, limit=avgPrice * 1.04",
            "trail_price=avgPrice * 1.02, trail_offset=40")
        self.assertNotIn("PINE031", codes(lint_text(literal)))

    # PINE032 — unguarded position_avg_price
    def test_pine032_unguarded_position_avg_price(self):
        text = VALID_STRATEGY.replace("if strategy.position_size > 0\n    ", "").replace(
            "    strategy.exit(", "strategy.exit(")
        self.assertIn("PINE032", codes(lint_text(text)))
        self.assertNotIn("PINE032", codes(lint_text(VALID_STRATEGY)))

    # PINE033 — qty range
    def test_pine033_qty_percent_out_of_range(self):
        for bad in ("qty_percent=0", "qty_percent=150", "qty_percent=-10"):
            text = VALID_STRATEGY.replace("stop=avgPrice * 0.98", bad + ", stop=avgPrice * 0.98")
            self.assertIn("PINE033", codes(lint_text(text)), msg=bad)

    def test_pine033_accepts_valid_qty(self):
        text = VALID_STRATEGY.replace('strategy.entry("Long", strategy.long)',
                                      'strategy.entry("Long", strategy.long, qty=2)')
        self.assertNotIn("PINE033", codes(lint_text(text)))
        percent = VALID_STRATEGY.replace("stop=avgPrice * 0.98",
                                         "qty_percent=50, stop=avgPrice * 0.98")
        self.assertNotIn("PINE033", codes(lint_text(percent)))

    # PINE034 — orphan from_entry
    def test_pine034_from_entry_typo(self):
        text = VALID_STRATEGY.replace('"Long Exit", "Long"', '"Long Exit", "Lonng"')
        self.assertIn("PINE034", codes(lint_text(text)))
        self.assertNotIn("PINE034", codes(lint_text(VALID_STRATEGY)))

    def test_pine034_skipped_for_dynamic_entry_ids(self):
        text = VALID_STRATEGY.replace(
            'strategy.entry("Long", strategy.long)',
            'strategy.entry(idVar, strategy.long)').replace(
            '"Long Exit", "Long"', '"Long Exit", "Whatever"')
        self.assertNotIn("PINE034", codes(lint_text(text)))

    # PINE035 — entries with no exits
    def test_pine035_entries_without_exits(self):
        text = VALID_STRATEGY.replace(
            'if strategy.position_size > 0\n'
            '    float avgPrice = strategy.position_avg_price\n'
            '    strategy.exit("Long Exit", "Long", stop=avgPrice * 0.98, limit=avgPrice * 1.04)\n',
            "")
        self.assertIn("PINE035", codes(lint_text(text)))
        self.assertNotIn("PINE035", codes(lint_text(VALID_STRATEGY)))

    def test_strategy_rules_dont_fire_on_indicators(self):
        result = lint_text(VALID_INDICATOR)
        for code in ("PINE029", "PINE030", "PINE031", "PINE032", "PINE033", "PINE034", "PINE035"):
            self.assertNotIn(code, codes(result))


class TestCli(unittest.TestCase):
    def test_json_output(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "script.pine"
            path.write_text('//@version=6\nindicator("X")\nplot(close)\n', encoding="utf-8")
            proc = run_script("pine_lint.py", path, "--json")
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertIn("findings", payload)
        self.assertIn("summary", payload)
        self.assertIn("PINE022", {f["code"] for f in payload["findings"]})

    def test_missing_file_exits_1(self):
        proc = run_script("pine_lint.py", "does_not_exist.pine")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not found", proc.stderr)


if __name__ == "__main__":
    unittest.main()
