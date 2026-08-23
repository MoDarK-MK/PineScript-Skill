import json
import tempfile
import unittest
from pathlib import Path

from tests.helpers import (
    REPO_ROOT, VALID_INDICATOR, VALID_STRATEGY, codes, lint_text, run_script)

import pine_lint


class TestRuleCatalog(unittest.TestCase):
    def test_catalog_endpoints_and_pine024(self):
        self.assertNotIn("PINE024", pine_lint.RULES)
        self.assertIn("PINE001", pine_lint.RULES)
        self.assertIn("PINE057", pine_lint.RULES)

    def test_list_rules_cli_prints_every_rule(self):
        # Derived from the catalog on purpose: a hand-maintained count here was
        # one more place to forget, and test_docs_consistency already pins the
        # catalog against the documentation.
        proc = run_script("pine_lint.py", "--list-rules")
        self.assertEqual(proc.returncode, 0)
        lines = [l for l in proc.stdout.splitlines() if l.strip()]
        self.assertEqual(len(lines), len(pine_lint.RULES))

    def test_fixable_rules_all_exist(self):
        unknown = sorted(pine_lint.FIXABLE - set(pine_lint.RULES))
        self.assertEqual([], unknown)


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

    # PINE045 — na compared with ==/!= never matches
    def test_pine045_flags_na_comparison(self):
        text = VALID_INDICATOR + (
            'var int cachedBar = na\n'
            'if barstate.islast and cachedBar != bar_index\n'
            '    cachedBar := bar_index\n'
        )
        self.assertIn("PINE045", codes(lint_text(text)))

    def test_pine045_accepts_an_na_guard(self):
        text = VALID_INDICATOR + (
            'var int cachedBar = na\n'
            'if barstate.islast and (na(cachedBar) or cachedBar != bar_index)\n'
            '    cachedBar := bar_index\n'
        )
        self.assertNotIn("PINE045", codes(lint_text(text)))

    def test_pine045_ignores_variables_not_initialised_to_na(self):
        text = VALID_INDICATOR + (
            'var int cachedBar = 0\n'
            'if barstate.islast and cachedBar != bar_index\n'
            '    cachedBar := bar_index\n'
        )
        self.assertNotIn("PINE045", codes(lint_text(text)))

    # PINE046 — input.*() is global-scope only
    def test_pine046_input_inside_a_block(self):
        text = VALID_INDICATOR + (
            'if close > open\n'
            '    int lenInside = input.int(14, "Length")\n'
            '    plot(lenInside, title="Len")\n'
        )
        self.assertIn("PINE046", codes(lint_text(text)))

    def test_pine046_input_inside_a_function(self):
        text = VALID_INDICATOR + (
            'getLen() =>\n'
            '    input.int(14, "Length")\n'
        )
        self.assertIn("PINE046", codes(lint_text(text)))

    def test_pine046_accepts_global_inputs_including_wrapped_ones(self):
        text = VALID_INDICATOR + (
            'int lenInput = input.int(\n'
            '     14, "Length", minval=1, maxval=100)\n'
            'plot(lenInput, title="Len")\n'
        )
        self.assertNotIn("PINE046", codes(lint_text(text)))

    # PINE047 — the plot family is global-scope only
    def test_pine047_plot_inside_a_block(self):
        text = VALID_INDICATOR + (
            'if close > open\n'
            '    plot(close, title="C")\n'
        )
        self.assertIn("PINE047", codes(lint_text(text)))

    def test_pine047_accepts_the_na_pattern(self):
        text = VALID_INDICATOR + (
            'bool showIt = input.bool(true, "Show")\n'
            'plot(showIt ? close : na, title="C")\n'
        )
        self.assertNotIn("PINE047", codes(lint_text(text)))

    def test_pine047_accepts_drawing_calls_inside_blocks(self):
        # line/label/box are NOT restricted to global scope — only the plot family.
        text = VALID_INDICATOR + (
            'if barstate.islast\n'
            '    label.new(bar_index, high, "x")\n'
        )
        self.assertNotIn("PINE047", codes(lint_text(text)))

    # PINE048 — the 40-request cap
    def test_pine048_flags_too_many_unique_requests(self):
        lines = [VALID_STRATEGY]
        for i in range(45):
            lines.append(
                f'float r{i} = request.security(syminfo.tickerid, "{i + 1}", close, '
                f'lookahead=barmerge.lookahead_off)\n')
        self.assertIn("PINE048", codes(lint_text("".join(lines))))

    def test_pine048_does_not_count_identical_calls_twice(self):
        call = ('request.security(syminfo.tickerid, "D", close, '
                'lookahead=barmerge.lookahead_off)')
        lines = [VALID_INDICATOR]
        for i in range(45):
            lines.append(f'float r{i} = {call}\n')
        # All 45 are the same call, so they share one series and one slot.
        self.assertNotIn("PINE048", codes(lint_text("".join(lines))))

    # PINE049 — strategy orders cannot live in a function
    def test_pine049_strategy_call_in_a_function(self):
        text = VALID_STRATEGY + (
            'placeIt(bool go) =>\n'
            '    if go\n'
            '        strategy.entry("Long", strategy.long)\n'
            '    0\n'
        )
        self.assertIn("PINE049", codes(lint_text(text)))

    def test_pine049_accepts_orders_at_global_scope(self):
        self.assertNotIn("PINE049", codes(lint_text(VALID_STRATEGY)))

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

    def test_explain_prints_the_rule_documentation(self):
        proc = run_script("pine_lint.py", "--explain", "PINE042")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("PINE042", proc.stdout)
        self.assertIn("CE10088", proc.stdout)

    def test_explain_accepts_a_bare_number(self):
        proc = run_script("pine_lint.py", "--explain", "45")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("PINE045", proc.stdout)

    def test_explain_rejects_an_unknown_rule(self):
        proc = run_script("pine_lint.py", "--explain", "PINE999")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("unknown rule", proc.stderr)

    def test_explain_covers_every_rule_in_the_catalog(self):
        """Guards against a rule shipping with no explainable documentation."""
        for code in sorted(pine_lint.RULES):
            proc = run_script("pine_lint.py", "--explain", code)
            self.assertEqual(proc.returncode, 0, f"{code}: {proc.stderr}")
            self.assertNotIn("no section in references", proc.stdout,
                             msg=f"{code} has no section in lint-rules.md")

    def test_baseline_round_trip_suppresses_existing_findings(self):
        with tempfile.TemporaryDirectory() as td:
            pine = Path(td) / "legacy.pine"
            pine.write_text('//@version=6\nindicator("Legacy")\nplot(close)\n', encoding="utf-8")
            baseline = Path(td) / "baseline.txt"

            dirty = run_script("pine_lint.py", pine, "--strict")
            self.assertEqual(dirty.returncode, 1)

            written = run_script("pine_lint.py", pine, "--write-baseline", baseline)
            self.assertEqual(written.returncode, 0, written.stderr)
            self.assertTrue(baseline.exists())

            clean = run_script("pine_lint.py", pine, "--strict", "--baseline", baseline)
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
            self.assertIn("suppressed", clean.stdout)

    def test_baseline_still_reports_a_new_problem(self):
        with tempfile.TemporaryDirectory() as td:
            pine = Path(td) / "legacy.pine"
            pine.write_text('//@version=6\nindicator("Legacy")\nplot(close)\n', encoding="utf-8")
            baseline = Path(td) / "baseline.txt"
            run_script("pine_lint.py", pine, "--write-baseline", baseline)
            # Introduce a defect the baseline does not cover.
            pine.write_text('//@version=6\nindicator("Legacy")\nplot(close)\n'
                            'x = math.max(1, 2\n', encoding="utf-8")
            proc = run_script("pine_lint.py", pine, "--baseline", baseline)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("PINE003", proc.stdout)

    def test_missing_file_exits_1(self):
        proc = run_script("pine_lint.py", "does_not_exist.pine")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not found", proc.stderr)


class TestSymbolTableRules(unittest.TestCase):
    """PINE050/PINE051 — the two rules backed by the symbol table."""

    def test_pine050_flags_assignment_to_undeclared_name(self):
        text = VALID_INDICATOR + (
            "atrLen = 14\n"
            "if timeframe.isdaily\n"
            "    atrLenght := 21\n"
            "plot(atrLen, title=\"L\")\n")
        self.assertIn("PINE050", codes(lint_text(text)))

    def test_pine050_accepts_a_correctly_declared_name(self):
        text = VALID_INDICATOR + (
            "var atrLen = 14\n"
            "if timeframe.isdaily\n"
            "    atrLen := 21\n"
            "plot(atrLen, title=\"L\")\n")
        self.assertNotIn("PINE050", codes(lint_text(text)))

    def test_pine050_accepts_a_function_parameter(self):
        text = VALID_INDICATOR + (
            "bump(int n) =>\n"
            "    n := n + 1\n"
            "    n\n"
            "plot(bump(1), title=\"B\")\n")
        self.assertNotIn("PINE050", codes(lint_text(text)))

    def test_pine050_accepts_a_loop_variable(self):
        text = VALID_INDICATOR + (
            "var float acc = 0.0\n"
            "for i = 0 to 3\n"
            "    i := i\n"
            "    acc := acc + 1\n"
            "plot(acc, title=\"A\")\n")
        self.assertNotIn("PINE050", codes(lint_text(text)))

    def test_pine050_ignores_member_assignment(self):
        text = VALID_INDICATOR + (
            "type Holder\n"
            "    float value\n"
            "var Holder h = Holder.new(0.0)\n"
            "h.value := close\n"
            "plot(h.value, title=\"V\")\n")
        self.assertNotIn("PINE050", codes(lint_text(text)))

    def test_pine051_flags_a_write_only_variable(self):
        text = VALID_INDICATOR + "unusedThing = ta.atr(14)\n"
        self.assertIn("PINE051", codes(lint_text(text)))

    def test_pine051_exempts_underscore_names(self):
        text = VALID_INDICATOR + "_discarded = ta.atr(14)\n"
        self.assertNotIn("PINE051", codes(lint_text(text)))

    def test_pine051_does_not_flag_a_used_variable(self):
        text = VALID_INDICATOR + "atr14 = ta.atr(14)\nplot(atr14, title=\"ATR\")\n"
        self.assertNotIn("PINE051", codes(lint_text(text)))

    def test_pine051_counts_a_read_inside_a_call(self):
        text = VALID_INDICATOR + (
            "lenIn = 14\n"
            "plot(ta.sma(close, lenIn), title=\"SMA\")\n")
        self.assertNotIn("PINE051", codes(lint_text(text)))

    def test_pine051_is_only_a_note(self):
        text = VALID_INDICATOR + "unusedThing = ta.atr(14)\n"
        result = lint_text(text)
        self.assertTrue(result.ok(strict=True), msg=[f.msg for f in result.findings])


class TestDrawingBudgetRule(unittest.TestCase):
    """PINE052 — the failure mode here is silence, which is why it is a rule."""

    LOOP_BODY = (
        "var array<box> pool = array.new<box>()\n"
        "for i = 0 to 99\n"
        "    array.push(pool, box.new(bar_index, close, bar_index, close))\n"
        "plot(close, title=\"C\")\n")

    def test_flags_box_new_in_a_loop_without_max_boxes_count(self):
        text = ('// This source code is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/\n'
                '//@version=6\n'
                'indicator("Pool", "P", overlay=true)\n' + self.LOOP_BODY)
        self.assertIn("PINE052", codes(lint_text(text)))

    def test_accepts_a_declared_max_boxes_count(self):
        text = ('// This source code is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/\n'
                '//@version=6\n'
                'indicator("Pool", "P", overlay=true, max_boxes_count=500)\n' + self.LOOP_BODY)
        self.assertNotIn("PINE052", codes(lint_text(text)))

    def test_does_not_flag_a_drawing_outside_a_loop(self):
        text = VALID_INDICATOR + 'box.new(bar_index, close, bar_index, close)\n'
        self.assertNotIn("PINE052", codes(lint_text(text)))


class TestLoopCostRule(unittest.TestCase):
    """PINE053 — worst case, resolved from input maxvals, never guessed."""

    def test_flags_a_nest_that_multiplies_past_the_budget(self):
        text = VALID_INDICATOR + (
            "lookback = input.int(300, \"Bars\", maxval=5000)\n"
            "rows = input.int(30, \"Rows\", maxval=500)\n"
            "var array<float> buf = array.new<float>(500, 0.0)\n"
            "for i = 0 to lookback\n"
            "    for r = 0 to rows\n"
            "        array.set(buf, r, array.get(buf, r) + volume[i])\n")
        self.assertIn("PINE053", codes(lint_text(text)))

    def test_accepts_a_single_loop_within_budget(self):
        text = VALID_INDICATOR + (
            "lookback = input.int(300, \"Bars\", maxval=5000)\n"
            "var float acc = 0.0\n"
            "for i = 0 to lookback\n"
            "    acc := acc + volume[i]\n"
            "plot(acc, title=\"A\")\n")
        self.assertNotIn("PINE053", codes(lint_text(text)))

    def test_stays_silent_when_a_bound_cannot_be_resolved(self):
        # The inner bound is computed at runtime. Guessing a number here would
        # be a lie, so the rule must say nothing at all.
        text = VALID_INDICATOR + (
            "lookback = input.int(300, \"Bars\", maxval=5000)\n"
            "var array<float> buf = array.new<float>(500, 0.0)\n"
            "for i = 0 to lookback\n"
            "    for r = startIdx to endIdx\n"
            "        array.set(buf, r, 1.0)\n")
        self.assertNotIn("PINE053", codes(lint_text(text)))

    def test_sibling_loops_are_additive_not_multiplicative(self):
        text = VALID_INDICATOR + (
            "outer = input.int(300, \"Outer\", maxval=400)\n"
            "a = input.int(30, \"A\", maxval=200)\n"
            "b = input.int(30, \"B\", maxval=200)\n"
            "var float acc = 0.0\n"
            "for i = 0 to outer\n"
            "    for x = 0 to a\n"
            "        acc := acc + 1\n"
            "    for y = 0 to b\n"
            "        acc := acc + 1\n"
            "plot(acc, title=\"A\")\n")
        # 400 x 201 = 80,400 — under budget. Multiplying the siblings together
        # would give 16 million and a warning nobody should act on.
        self.assertNotIn("PINE053", codes(lint_text(text)))


class TestAutoFix(unittest.TestCase):
    BROKEN = (
        'study("X", overlay=true)\n'
        'plot(security(syminfo.tickerid, "D", close), title="D", linewidth=0)\n'
        'label.new(bar_index, close, "note // not a comment", size=size.large)\n')

    def test_fix_rewrites_every_mechanical_defect(self):
        with tempfile.TemporaryDirectory() as td:
            pine = Path(td) / "legacy.pine"
            pine.write_text(self.BROKEN, encoding="utf-8")
            proc = run_script("pine_lint.py", pine, "--fix")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            after = pine.read_text(encoding="utf-8")
            self.assertIn("indicator(", after)
            self.assertIn("request.security(", after)
            self.assertIn("linewidth=1", after)
            self.assertIn("size.normal", after)
            self.assertNotIn("study(", after)

    def test_fix_leaves_string_contents_alone(self):
        with tempfile.TemporaryDirectory() as td:
            pine = Path(td) / "legacy.pine"
            pine.write_text(self.BROKEN, encoding="utf-8")
            run_script("pine_lint.py", pine, "--fix")
            # The "// not a comment" text lives inside a string literal; treating
            # it as a comment would silently truncate the line.
            self.assertIn('"note // not a comment"', pine.read_text(encoding="utf-8"))

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            pine = Path(td) / "legacy.pine"
            pine.write_text(self.BROKEN, encoding="utf-8")
            proc = run_script("pine_lint.py", pine, "--fix", "--dry-run")
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(self.BROKEN, pine.read_text(encoding="utf-8"))
            self.assertIn("Re-run without --dry-run", proc.stdout)

    def test_fix_converts_leading_tabs(self):
        with tempfile.TemporaryDirectory() as td:
            pine = Path(td) / "tabs.pine"
            pine.write_text('//@version=6\nindicator("T", overlay=true)\n'
                            'if close > open\n\tx = 1\nplot(close, title="C")\n',
                            encoding="utf-8")
            run_script("pine_lint.py", pine, "--fix")
            self.assertNotIn("\t", pine.read_text(encoding="utf-8"))

    def test_fix_reports_when_there_is_nothing_to_do(self):
        with tempfile.TemporaryDirectory() as td:
            pine = Path(td) / "clean.pine"
            pine.write_text(VALID_INDICATOR, encoding="utf-8")
            proc = run_script("pine_lint.py", pine, "--fix")
            self.assertEqual(proc.returncode, 0)
            self.assertIn("nothing to fix", proc.stdout)


if __name__ == "__main__":
    unittest.main()

class TestVarCollectionRealtimeGrowth(unittest.TestCase):
    """PINE054. The negative cases matter more than the positive one here: the
    drawing-pool idiom is everywhere in this repo and must never be flagged."""

    def test_unguarded_push_is_flagged(self):
        src = """//@version=6
indicator("T", overlay=true)
var array<float> levels = array.new<float>()
float ph = ta.pivothigh(high, 5, 5)
if not na(ph)
    array.push(levels, ph)
plot(close, title="C")
"""
        self.assertIn("PINE054", codes(lint_text(src)))

    def test_confirmed_guard_clears_it(self):
        src = """//@version=6
indicator("T", overlay=true)
var array<float> levels = array.new<float>()
float ph = ta.pivothigh(high, 5, 5)
if not na(ph) and barstate.isconfirmed
    array.push(levels, ph)
plot(close, title="C")
"""
        self.assertNotIn("PINE054", codes(lint_text(src)))

    def test_outer_guard_counts(self):
        src = """//@version=6
indicator("T", overlay=true)
var array<float> levels = array.new<float>()
if barstate.isconfirmed
    if close > open
        array.push(levels, close)
plot(close, title="C")
"""
        self.assertNotIn("PINE054", codes(lint_text(src)))

    def test_drawing_pool_growth_is_exempt(self):
        src = """//@version=6
indicator("T", overlay=true, max_boxes_count=500)
var array<box> pool = array.new<box>()
if barstate.islast
    while array.size(pool) < 10
        array.push(pool, box.new(bar_index, close, bar_index, close))
plot(close, title="C")
"""
        self.assertNotIn("PINE054", codes(lint_text(src)))

    def test_cleared_scratch_buffer_is_exempt(self):
        src = """//@version=6
indicator("T", overlay=true)
var array<float> scratch = array.new<float>()
if barstate.islast
    array.clear(scratch)
    if close > open
        array.push(scratch, close)
plot(close, title="C")
"""
        self.assertNotIn("PINE054", codes(lint_text(src)))

    def test_unconditional_global_push_is_exempt(self):
        src = """//@version=6
indicator("T", overlay=true)
var array<float> closes = array.new<float>()
array.push(closes, close)
plot(close, title="C")
"""
        self.assertNotIn("PINE054", codes(lint_text(src)))


class TestForwardGlobalReference(unittest.TestCase):
    """PINE055. The negative cases carry the weight: a rule that flagged normal
    top-to-bottom code would be unusable."""

    def test_function_reading_a_later_global_is_flagged(self):
        src = """//@version=6
indicator("T", overlay=true)
readIt() =>
    laterValue * 2
float laterValue = ta.sma(close, 20)
plot(readIt(), title="X")
"""
        self.assertIn("PINE055", codes(lint_text(src)))

    def test_declaration_above_the_function_is_fine(self):
        src = """//@version=6
indicator("T", overlay=true)
float earlierValue = ta.sma(close, 20)
readIt() =>
    earlierValue * 2
plot(readIt(), title="X")
"""
        self.assertNotIn("PINE055", codes(lint_text(src)))

    def test_parameters_are_not_forward_references(self):
        src = """//@version=6
indicator("T", overlay=true)
scale(float value, float factor) =>
    value * factor
float value = 1.0
float factor = 2.0
plot(scale(close, 2), title="X")
"""
        self.assertNotIn("PINE055", codes(lint_text(src)))

    def test_function_locals_are_not_forward_references(self):
        src = """//@version=6
indicator("T", overlay=true)
compute() =>
    float temp = close * 2
    temp + 1
float temp = 5.0
plot(compute(), title="X")
"""
        self.assertNotIn("PINE055", codes(lint_text(src)))

    def test_loop_variables_are_not_forward_references(self):
        src = """//@version=6
indicator("T", overlay=true)
total(array<float> src) =>
    float acc = 0.0
    for item in src
        acc += item
    acc
float item = 1.0
var array<float> buf = array.new<float>()
plot(total(buf), title="X")
"""
        self.assertNotIn("PINE055", codes(lint_text(src)))


class TestUnusedFunction(unittest.TestCase):
    def test_uncalled_function_is_flagged(self):
        src = """//@version=6
indicator("T", overlay=true)
orphan(float v) =>
    v * 2
plot(close, title="C")
"""
        self.assertIn("PINE056", codes(lint_text(src)))

    def test_called_function_is_not(self):
        src = """//@version=6
indicator("T", overlay=true)
used(float v) =>
    v * 2
plot(used(close), title="C")
"""
        self.assertNotIn("PINE056", codes(lint_text(src)))

    def test_a_function_called_only_from_another_function_counts_as_used(self):
        src = """//@version=6
indicator("T", overlay=true)
inner(float v) =>
    v * 2
outer(float v) =>
    inner(v) + 1
plot(outer(close), title="C")
"""
        self.assertNotIn("PINE056", codes(lint_text(src)))

    def test_exported_library_functions_are_exempt(self):
        src = """//@version=6
library("T")
export helper(float v) =>
    v * 2
"""
        self.assertNotIn("PINE056", codes(lint_text(src)))


class TestConstantCondition(unittest.TestCase):
    def test_literal_true_is_flagged(self):
        src = """//@version=6
indicator("T", overlay=true)
if true
    label.new(bar_index, high, "debug")
plot(close, title="C")
"""
        self.assertIn("PINE057", codes(lint_text(src)))

    def test_literal_comparison_is_flagged(self):
        src = """//@version=6
indicator("T", overlay=true)
float x = 0.0
if 2 > 1
    x := 1.0
plot(x, title="C")
"""
        self.assertIn("PINE057", codes(lint_text(src)))

    def test_self_comparison_is_flagged(self):
        src = """//@version=6
indicator("T", overlay=true)
float value = close
float x = 0.0
if value == value
    x := 1.0
plot(x, title="C")
"""
        self.assertIn("PINE057", codes(lint_text(src)))

    def test_a_real_condition_is_not(self):
        src = """//@version=6
indicator("T", overlay=true)
float x = 0.0
if close > open
    x := 1.0
plot(x, title="C")
"""
        self.assertNotIn("PINE057", codes(lint_text(src)))

