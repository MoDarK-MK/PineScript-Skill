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
    def test_has_43_rules_and_no_pine024(self):
        self.assertEqual(len(pine_lint.RULES), 43)
        self.assertNotIn("PINE024", pine_lint.RULES)
        self.assertIn("PINE001", pine_lint.RULES)
        self.assertIn("PINE044", pine_lint.RULES)

    def test_list_rules_cli(self):
        proc = run_script("pine_lint.py", "--list-rules")
        self.assertEqual(proc.returncode, 0)
        lines = [l for l in proc.stdout.splitlines() if l.strip()]
        self.assertEqual(len(lines), 43)


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

    def test_wrapped_function_signature_not_flagged_as_empty_block(self):
        # Regression: a signature wrapped across lines ends the `=>` on a
        # continuation indented deeper than the body, which used to trip PINE020.
        text = VALID_INDICATOR + (
            'buildText(bool aFlag, bool bFlag,\n'
            '     bool cFlag, bool dFlag) =>\n'
            '    string out = aFlag ? "a" : "b"\n'
            '    out\n'
            'plotchar(close, "S", "", location.top)\n'
        )
        self.assertNotIn("PINE020", codes(lint_text(text)))

    def test_local_string_builder_not_flagged_as_accumulator(self):
        # A builder declared inside a function body is local; `var` would be wrong.
        text = VALID_INDICATOR + (
            'starString(int score) =>\n'
            '    string stars = ""\n'
            '    for i = 1 to 5\n'
            '        stars := stars + (i <= score ? "*" : "-")\n'
            '    stars\n'
            'plotchar(close, "S", "", location.top)\n'
        )
        self.assertNotIn("PINE005", codes(lint_text(text)))

    def test_global_accumulator_still_flagged(self):
        # The real bug PINE005 exists for: a global that resets every bar.
        text = VALID_INDICATOR + (
            'total = 0.0\n'
            'if close > open\n'
            '    total := total + volume\n'
            'plot(total, title="Total")\n'
        )
        self.assertIn("PINE005", codes(lint_text(text)))

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


class TestVisualAndPerfRules(unittest.TestCase):
    # PINE036 — invisible table text
    def test_pine036_cell_without_text_color(self):
        method_form = VALID_INDICATOR + (
            'var table t = table.new(position.top_right, 2, 1)\n'
            'if barstate.islast\n'
            '    t.cell(0, 0, "Trend", text_size=size.small)\n'
        )
        self.assertIn("PINE036", codes(lint_text(method_form)))
        func_form = VALID_INDICATOR + (
            'var table t = table.new(position.top_right, 2, 1)\n'
            'if barstate.islast\n'
            '    table.cell(t, 0, 0, "Trend", text_size=size.small)\n'
        )
        self.assertIn("PINE036", codes(lint_text(func_form)))

    def test_pine036_accepts_explicit_text_color(self):
        for call in ('t.cell(0, 0, "Trend", text_color=color.gray)',
                     'table.cell(t, 0, 0, "Trend", text_color=color.gray)'):
            text = VALID_INDICATOR + (
                'var table t = table.new(position.top_right, 2, 1)\n'
                'if barstate.islast\n'
                '    ' + call + '\n')
            self.assertNotIn("PINE036", codes(lint_text(text)), msg=call)

    def test_pine036_ignores_spacer_cells(self):
        text = VALID_INDICATOR + (
            'var table t = table.new(position.top_right, 2, 1)\n'
            'if barstate.islast\n'
            '    t.cell(0, 0, "")\n'
        )
        self.assertNotIn("PINE036", codes(lint_text(text)))

    # PINE037 — array reallocated every execution
    def test_pine037_array_new_in_block_without_var(self):
        text = VALID_INDICATOR + (
            'if barstate.islast\n'
            '    array<float> bins = array.new<float>(20, 0.0)\n'
            '    array.set(bins, 0, close)\n'
        )
        self.assertIn("PINE037", codes(lint_text(text)))

    def test_pine037_accepts_var_and_global_and_function_local(self):
        with_var = VALID_INDICATOR + (
            'if barstate.islast\n'
            '    var array<float> bins = array.new<float>(20, 0.0)\n'
            '    array.fill(bins, 0.0)\n'
        )
        self.assertNotIn("PINE037", codes(lint_text(with_var)))
        at_global = VALID_INDICATOR + 'array<float> bins = array.new<float>(20, 0.0)\n'
        self.assertNotIn("PINE037", codes(lint_text(at_global)))
        # A temporary inside a function body is a normal local, not per-bar churn.
        in_function = VALID_INDICATOR + (
            'buildBins(int n) =>\n'
            '    array<float> bins = array.new<float>(n, 0.0)\n'
            '    bins\n'
        )
        self.assertNotIn("PINE037", codes(lint_text(in_function)))

    # PINE038 — drawing churn
    def test_pine038_delete_and_recreate_in_barstate_block(self):
        text = VALID_INDICATOR + (
            'var line ln = na\n'
            'if barstate.islast\n'
            '    line.delete(ln)\n'
            '    ln := line.new(bar_index - 10, close, bar_index, close)\n'
        )
        self.assertIn("PINE038", codes(lint_text(text)))

    def test_pine038_accepts_incremental_update(self):
        text = VALID_INDICATOR + (
            'var line ln = line.new(na, na, na, na)\n'
            'if barstate.islast\n'
            '    line.set_xy1(ln, bar_index - 10, close)\n'
            '    line.set_xy2(ln, bar_index, close)\n'
        )
        self.assertNotIn("PINE038", codes(lint_text(text)))

    # PINE039 — mergeable requests
    def test_pine039_duplicate_security_call(self):
        text = VALID_INDICATOR + (
            'float a = request.security(syminfo.tickerid, "D", high[1], '
            'lookahead=barmerge.lookahead_on)\n'
            'float b = request.security(syminfo.tickerid, "D", low[1], '
            'lookahead=barmerge.lookahead_on)\n'
            'plot(a + b, title="Sum")\n'
        )
        self.assertIn("PINE039", codes(lint_text(text)))

    def test_pine039_accepts_distinct_and_merged_calls(self):
        distinct = VALID_INDICATOR + (
            'float a = request.security(syminfo.tickerid, "D", high[1], '
            'lookahead=barmerge.lookahead_on)\n'
            'float b = request.security(syminfo.tickerid, "W", low[1], '
            'lookahead=barmerge.lookahead_on)\n'
            'plot(a + b, title="Sum")\n'
        )
        self.assertNotIn("PINE039", codes(lint_text(distinct)))
        merged = VALID_INDICATOR + (
            '[a, b] = request.security(syminfo.tickerid, "D", [high[1], low[1]], '
            'lookahead=barmerge.lookahead_on)\n'
            'plot(a + b, title="Sum")\n'
        )
        self.assertNotIn("PINE039", codes(lint_text(merged)))

    # PINE040 — untitled plots
    def test_pine040_plot_without_title(self):
        text = VALID_INDICATOR + "plot(ta.sma(close, 20))\n"
        self.assertIn("PINE040", codes(lint_text(text)))

    def test_pine040_accepts_positional_and_named_titles(self):
        positional = VALID_INDICATOR + 'plot(ta.sma(close, 20), "SMA")\n'
        self.assertNotIn("PINE040", codes(lint_text(positional)))
        named = VALID_INDICATOR + 'plot(ta.sma(close, 20), title="SMA")\n'
        self.assertNotIn("PINE040", codes(lint_text(named)))

    # PINE041 — oversized chart text
    def test_pine041_flags_large_and_huge(self):
        for size_name in ("size.large", "size.huge"):
            text = VALID_INDICATOR + (
                f'label.new(bar_index, high, "X", size={size_name})\n')
            self.assertIn("PINE041", codes(lint_text(text)), msg=size_name)

    def test_pine041_accepts_normal_and_below(self):
        text = VALID_INDICATOR + 'label.new(bar_index, high, "X", size=size.normal)\n'
        self.assertNotIn("PINE041", codes(lint_text(text)))

    # PINE042 — Pine forbids a function mutating a global (CE10088)
    def test_pine042_function_mutates_global(self):
        text = VALID_INDICATOR + (
            'var int passCount = 0\n'
            'bump(bool ok) =>\n'
            '    if ok\n'
            '        passCount += 1\n'
            '    0\n'
        )
        self.assertIn("PINE042", codes(lint_text(text)))

    def test_pine042_accepts_locals_params_and_object_fields(self):
        # A local, a parameter's array, and a UDT field are all legal to mutate.
        text = VALID_INDICATOR + (
            'var int passCount = 0\n'
            'build(array<float> arr) =>\n'
            '    float total = 0.0\n'
            '    total := total + 1\n'
            '    array.push(arr, total)\n'
            '    total\n'
        )
        self.assertNotIn("PINE042", codes(lint_text(text)))

    def test_pine042_accepts_global_mutation_outside_a_function(self):
        text = VALID_INDICATOR + (
            'var int counter = 0\n'
            'if close > open\n'
            '    counter += 1\n'
            'plot(counter, title="Counter")\n'
        )
        self.assertNotIn("PINE042", codes(lint_text(text)))

    # PINE043 — trailing if/else with mismatched branch types (CE10235)
    def test_pine043_trailing_branches_return_different_types(self):
        text = VALID_INDICATOR + (
            'record(bool ok, string msg) =>\n'
            '    int n = 0\n'
            '    if ok\n'
            '        n := n + 1\n'
            '    else\n'
            '        label.new(bar_index, high, msg)\n'
        )
        self.assertIn("PINE043", codes(lint_text(text)))

    def test_pine043_accepts_a_trailing_plain_expression(self):
        text = VALID_INDICATOR + (
            'record(bool ok, string msg) =>\n'
            '    if not ok\n'
            '        label.new(bar_index, high, msg)\n'
            '    ok ? 0 : 1\n'
        )
        self.assertNotIn("PINE043", codes(lint_text(text)))

    # PINE044 — seconds timeframes need a Premium plan
    def test_pine044_flags_seconds_timeframe(self):
        text = VALID_INDICATOR + (
            'float x = request.security(syminfo.tickerid, "5S", close, '
            'lookahead=barmerge.lookahead_off)\n'
            'plot(x, title="X")\n'
        )
        self.assertIn("PINE044", codes(lint_text(text)))

    def test_pine044_is_advisory_and_does_not_fail_strict(self):
        text = VALID_INDICATOR + (
            'float x = request.security(syminfo.tickerid, "5S", close, '
            'lookahead=barmerge.lookahead_off)\n'
            'plot(x, title="X")\n'
        )
        result = lint_text(text)
        self.assertTrue(result.ok(strict=True))

    def test_pine044_ignores_minute_timeframes(self):
        text = VALID_INDICATOR + (
            'float x = request.security(syminfo.tickerid, "5", close, '
            'lookahead=barmerge.lookahead_off)\n'
            'plot(x, title="X")\n'
        )
        self.assertNotIn("PINE044", codes(lint_text(text)))

    def test_pine044_reports_once_per_file(self):
        text = VALID_INDICATOR + (
            'string a = "1S"\n'
            'string b = "5S"\n'
            'string c = "15S"\n'
            'plot(close, title="C")\n'
        )
        seconds_findings = [f for f in lint_text(text).findings if f.code == "PINE044"]
        self.assertEqual(1, len(seconds_findings))

    # PINE022 rescoped to the declaration statement
    def test_pine022_ignores_overlay_mentioned_only_in_a_comment(self):
        text = (
            "//@version=6\n"
            'indicator("X")\n'
            "// this script deliberately leaves overlay= at the default\n"
            "plot(close, title=\"Close\")\n"
        )
        self.assertIn("PINE022", codes(lint_text(text)))


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
