"""Tests for the 16 rules that had none.

They were found by scripts/mutate_check.py, which disables one rule at a time
and re-runs the suite: any rule whose absence changes nothing is a rule that
could be deleted in a refactor with no test going red. Sixteen of fifty-two
were in that state — nearly a third of the catalog, all of it invisible while
the suite reported OK.

Each rule gets a positive case (the defect is reported) and a negative case
(the correct form is not). The negative half matters more than it looks: a rule
that fires on everything also "passes" every positive test.
"""
import unittest

from tests.helpers import VALID_INDICATOR, codes, lint_text

HEADER = ('// This source code is subject to the terms of the Mozilla Public License 2.0 '
          'at https://mozilla.org/MPL/2.0/\n//@version=6\n')


class TestSecurityLookahead(unittest.TestCase):
    """PINE006 — the choice must be visible. See references/mtf-guide.md §2."""

    def test_flags_security_without_lookahead(self):
        text = VALID_INDICATOR + 'd = request.security(syminfo.tickerid, "D", close)\n'
        self.assertIn("PINE006", codes(lint_text(text)))

    def test_accepts_an_explicit_lookahead(self):
        text = VALID_INDICATOR + ('d = request.security(syminfo.tickerid, "D", close[1], '
                                  'lookahead=barmerge.lookahead_on)\n')
        self.assertNotIn("PINE006", codes(lint_text(text)))


class TestInputTitle(unittest.TestCase):
    """PINE007 — an untitled input shows the variable name in the panel."""

    def test_flags_input_without_a_title(self):
        text = VALID_INDICATOR + "len = input.int(14)\nplot(ta.sma(close, len), title=\"S\")\n"
        self.assertIn("PINE007", codes(lint_text(text)))

    def test_accepts_a_titled_input(self):
        text = VALID_INDICATOR + ('len = input.int(14, "Length")\n'
                                  'plot(ta.sma(close, len), title="S")\n')
        self.assertNotIn("PINE007", codes(lint_text(text)))


class TestPlotCountLimit(unittest.TestCase):
    """PINE009 — 64 plot counts, and some calls consume up to 7 each."""

    def test_flags_going_over_the_plot_budget(self):
        text = VALID_INDICATOR + "".join(
            f'plot(close + {i}, title="p{i}")\n' for i in range(70))
        self.assertIn("PINE009", codes(lint_text(text)))

    def test_accepts_a_handful_of_plots(self):
        text = VALID_INDICATOR + "".join(
            f'plot(close + {i}, title="p{i}")\n' for i in range(5))
        self.assertNotIn("PINE009", codes(lint_text(text)))


class TestLinewidthMinimum(unittest.TestCase):
    """PINE012 — v6 rejects a linewidth below 1. --fix repairs it."""

    def test_flags_zero_linewidth(self):
        text = VALID_INDICATOR + 'plot(close, title="Z", linewidth=0)\n'
        self.assertIn("PINE012", codes(lint_text(text)))

    def test_accepts_linewidth_one(self):
        text = VALID_INDICATOR + 'plot(close, title="Z", linewidth=1)\n'
        self.assertNotIn("PINE012", codes(lint_text(text)))


class TestSwitchDefault(unittest.TestCase):
    """PINE013 — v6 requires the default arm that v5 let you omit."""

    def test_flags_switch_without_a_default_arm(self):
        text = VALID_INDICATOR + (
            'pick(string k) =>\n'
            '    switch k\n'
            '        "a" => 1\n'
            '        "b" => 2\n'
            'plot(pick("a"), title="P")\n')
        self.assertIn("PINE013", codes(lint_text(text)))

    def test_accepts_a_switch_with_a_default_arm(self):
        text = VALID_INDICATOR + (
            'pick(string k) =>\n'
            '    switch k\n'
            '        "a" => 1\n'
            '        => 0\n'
            'plot(pick("a"), title="P")\n')
        self.assertNotIn("PINE013", codes(lint_text(text)))


class TestHistoryOnLiteral(unittest.TestCase):
    """PINE014 — only variables and series can be history-referenced in v6."""

    def test_flags_history_on_a_numeric_literal(self):
        text = VALID_INDICATOR + "x = 5[1]\nplot(x, title=\"X\")\n"
        self.assertIn("PINE014", codes(lint_text(text)))

    def test_accepts_history_on_a_series(self):
        text = VALID_INDICATOR + "x = close[1]\nplot(x, title=\"X\")\n"
        self.assertNotIn("PINE014", codes(lint_text(text)))


class TestDuplicateNamedParams(unittest.TestCase):
    """PINE015 — the same named argument twice is a v6 compile error."""

    def test_flags_a_repeated_named_parameter(self):
        text = VALID_INDICATOR + 'plot(close, title="A", title="B")\n'
        self.assertIn("PINE015", codes(lint_text(text)))

    def test_accepts_distinct_named_parameters(self):
        text = VALID_INDICATOR + 'plot(close, title="A", linewidth=2)\n'
        self.assertNotIn("PINE015", codes(lint_text(text)))


class TestTimeframeCompare(unittest.TestCase):
    """PINE016 — timeframe.period always carries a multiplier."""

    def test_flags_comparison_to_a_bare_unit(self):
        text = VALID_INDICATOR + 'isDaily = timeframe.period == "D"\nplot(isDaily ? 1 : 0, title="D")\n'
        self.assertIn("PINE016", codes(lint_text(text)))

    def test_accepts_a_seconds_based_comparison(self):
        text = VALID_INDICATOR + ('isIntraday = timeframe.in_seconds() < timeframe.in_seconds("60")\n'
                                  'plot(isIntraday ? 1 : 0, title="I")\n')
        self.assertNotIn("PINE016", codes(lint_text(text)))


class TestLazyEvalTrap(unittest.TestCase):
    """PINE017 — v6 short-circuits, so a ta.* call after and/or may not run on
    every bar, which corrupts anything with internal state."""

    def test_flags_a_ta_call_after_an_and(self):
        text = VALID_INDICATOR + ('sig = close > open and ta.rsi(close, 14) > 70\n'
                                  'plot(sig ? 1 : 0, title="S")\n')
        self.assertIn("PINE017", codes(lint_text(text)))

    def test_accepts_the_call_hoisted_above_the_condition(self):
        text = VALID_INDICATOR + ('rsiValue = ta.rsi(close, 14)\n'
                                  'sig = close > open and rsiValue > 70\n'
                                  'plot(sig ? 1 : 0, title="S")\n')
        self.assertNotIn("PINE017", codes(lint_text(text)))


class TestNamingConvention(unittest.TestCase):
    """PINE018 — camelCase for variables, SNAKE_CASE reserved for constants."""

    def test_flags_snake_case(self):
        text = VALID_INDICATOR + 'my_length = 14\nplot(ta.sma(close, my_length), title="S")\n'
        self.assertIn("PINE018", codes(lint_text(text)))

    def test_flags_pascal_case(self):
        text = VALID_INDICATOR + 'MyLength = 14\nplot(ta.sma(close, MyLength), title="S")\n'
        self.assertIn("PINE018", codes(lint_text(text)))

    def test_accepts_camel_case_and_all_caps_constants(self):
        text = VALID_INDICATOR + ('myLength = 14\nMAX_LENGTH = 50\n'
                                  'plot(ta.sma(close, math.min(myLength, MAX_LENGTH)), title="S")\n')
        self.assertNotIn("PINE018", codes(lint_text(text)))


class TestIndentationConsistency(unittest.TestCase):
    """PINE019 / PINE026 — Pine treats indentation structurally, so mixing is
    not a cosmetic problem."""

    def test_flags_tabs_and_spaces_in_one_line(self):
        text = HEADER + 'indicator("X", overlay=true)\nif close > open\n \tx = 1\nplot(close, title="C")\n'
        self.assertIn("PINE019", codes(lint_text(text)))

    def test_flags_a_file_mixing_both_styles(self):
        text = (HEADER + 'indicator("X", overlay=true)\n'
                'if close > open\n    x = 1\n'
                'if close < open\n\ty = 1\n'
                'plot(close, title="C")\n')
        self.assertIn("PINE026", codes(lint_text(text)))

    def test_accepts_consistent_space_indentation(self):
        text = (HEADER + 'indicator("X", overlay=true)\n'
                'if close > open\n    x = 1\n'
                'if close < open\n    y = 1\n'
                'plot(close, title="C")\n')
        found = codes(lint_text(text))
        self.assertNotIn("PINE019", found)
        self.assertNotIn("PINE026", found)


class TestBlockHeaderBody(unittest.TestCase):
    """PINE020 — a block header with nothing indented under it."""

    def test_flags_an_empty_if_block(self):
        text = HEADER + 'indicator("X", overlay=true)\nif close > open\nplot(close, title="C")\n'
        self.assertIn("PINE020", codes(lint_text(text)))

    def test_accepts_an_if_with_a_body(self):
        text = (HEADER + 'indicator("X", overlay=true)\n'
                'var float x = 0.0\nif close > open\n    x := 1.0\nplot(x, title="X")\n')
        self.assertNotIn("PINE020", codes(lint_text(text)))


class TestIntDivisionLiterals(unittest.TestCase):
    """PINE023 — v6 returns a fraction where v5 truncated const ints."""

    def test_flags_an_uneven_literal_division(self):
        text = VALID_INDICATOR + "half = 7 / 2\nplot(half, title=\"H\")\n"
        self.assertIn("PINE023", codes(lint_text(text)))

    def test_accepts_an_even_literal_division(self):
        text = VALID_INDICATOR + "half = 8 / 2\nplot(half, title=\"H\")\n"
        self.assertNotIn("PINE023", codes(lint_text(text)))

    def test_is_only_a_note(self):
        text = VALID_INDICATOR + "half = 7 / 2\nplot(half, title=\"H\")\n"
        self.assertTrue(lint_text(text).ok(strict=True))


class TestDrawingLimits(unittest.TestCase):
    """PINE025 — counts call sites against the default 50 and the hard 500.
    PINE052 is its companion for drawings created in a loop."""

    def test_flags_more_call_sites_than_the_default_cap(self):
        text = VALID_INDICATOR + "".join(
            f"label.new(bar_index, close, \"L{i}\")\n" for i in range(60))
        self.assertIn("PINE025", codes(lint_text(text)))

    def test_accepts_the_same_count_with_the_limit_declared(self):
        text = (HEADER + 'indicator("X", "X", overlay=true, max_labels_count=500)\n'
                + "".join(f"label.new(bar_index, close, \"L{i}\")\n" for i in range(60))
                + 'plot(close, title="C")\n')
        self.assertNotIn("PINE025", codes(lint_text(text)))


class TestVersionPragmaPosition(unittest.TestCase):
    """PINE028 — the pragma is legal anywhere, but code above it is a trap for
    the reader, who assumes the top of the file tells them the version."""

    def test_flags_code_before_the_pragma(self):
        text = 'myConst = 5\n//@version=6\nindicator("X", overlay=true)\nplot(close, title="C")\n'
        self.assertIn("PINE028", codes(lint_text(text)))

    def test_accepts_comments_before_the_pragma(self):
        self.assertNotIn("PINE028", codes(lint_text(VALID_INDICATOR)))


if __name__ == "__main__":
    unittest.main()
