"""Tests for the Pine interpreter.

The cases here are chosen for one reason: each is a semantic that a plausible
implementation gets WRONG, and getting it wrong would make every result the
interpreter produces quietly untrustworthy rather than obviously broken.

Three of them are regressions for bugs this interpreter actually had:
  - `else` branches ran unconditionally, because the parser read the enclosing
    indent after the body had already changed it
  - a string literal "-" was parsed as a unary minus, because operator tests
    compared token text without checking token kind
  - `1e-10` lexed as `1`, `e`, `-10`
"""
import unittest
from pathlib import Path

from tests.helpers import REPO_ROOT

import sys
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from pine_interp import (PineRuntimeError, PineSyntaxError, Platform,
                         run_file, run_source, synthetic_bars)

BARS = synthetic_bars(60)


def head(body, decl='indicator("T", overlay=true)'):
    return "//@version=6\n" + decl + "\n" + body


class TestExecutionModel(unittest.TestCase):
    def test_var_initialises_once_and_persists(self):
        r = run_source(head("""
var int seen = 0
seen += 1
plot(seen, title="n")
"""), BARS)
        self.assertEqual(len(BARS), r.last("n"))

    def test_plain_declaration_re_runs_every_bar(self):
        r = run_source(head("""
int seen = 0
seen += 1
plot(seen, title="n")
"""), BARS)
        self.assertEqual(1, r.last("n"))

    def test_history_reaches_back(self):
        r = run_source(head("""
float prev = close[1]
float older = close[3]
plot(prev, title="p")
plot(older, title="o")
"""), BARS)
        self.assertAlmostEqual(BARS[-2]["close"], r.last("p"))
        self.assertAlmostEqual(BARS[-4]["close"], r.last("o"))

    def test_history_before_the_start_is_na(self):
        r = run_source(head('plot(close[500], title="p")'), BARS)
        self.assertIsNone(r.last("p"))


class TestPineSemantics(unittest.TestCase):
    def test_na_never_equals_na(self):
        """The trap PINE045 exists for. If the interpreter said na == na is
        true, it would hide exactly the bug it should reveal."""
        r = run_source(head("""
float a = na
float b = na
plot(a == b ? 1 : 0, title="eq")
plot(na(a) ? 1 : 0, title="isna")
"""), BARS)
        self.assertEqual(0, r.last("eq"))
        self.assertEqual(1, r.last("isna"))

    def test_a_for_loop_counts_down_when_the_end_is_lower(self):
        """Pine's genuine behaviour, and a real bug this repo shipped:
        `for i = 0 to size - 1` on an empty array runs with i = 0 and i = -1."""
        r = run_source(head("""
var array<int> seen = array.new<int>(0)
if bar_index == 1
    for i = 0 to -1
        array.push(seen, i)
plot(array.size(seen), title="n")
"""), BARS)
        self.assertEqual(2, r.last("n"))

    def test_arithmetic_with_na_yields_na(self):
        r = run_source(head("""
float a = na
plot(a + 1, title="sum")
"""), BARS)
        self.assertIsNone(r.last("sum"))

    def test_and_short_circuits(self):
        """`na(x) or x != y` depends on it, and so does every guard built that
        way in this repo."""
        r = run_source(head("""
var array<int> calls = array.new<int>(0)
bump() =>
    array.push(calls, 1)
    true
bool result = false and bump()
plot(array.size(calls), title="n")
"""), BARS)
        self.assertEqual(0, r.last("n"))


class TestParserRegressions(unittest.TestCase):
    def test_else_runs_only_when_the_condition_is_false(self):
        """Regression. The enclosing indent was read AFTER the body had been
        parsed, so `else` never matched its `if`, was parsed as a separate
        statement, and its body ran on every pass."""
        r = run_source(head("""
var int taken = 0
var int other = 0
if close > 0
    taken += 1
else
    other += 1
plot(taken, title="t")
plot(other, title="o")
"""), BARS)
        self.assertEqual(len(BARS), r.last("t"))
        self.assertEqual(0, r.last("o"))

    def test_else_if_chain(self):
        r = run_source(head("""
int which = 0
if false
    which := 1
else if true
    which := 2
else
    which := 3
plot(which, title="w")
"""), BARS)
        self.assertEqual(2, r.last("w"))

    def test_a_string_containing_an_operator_is_not_an_operator(self):
        """Regression. `cur().value == "-"` is true for the STRING "-", so
        `(v >= 0 ? "+" : "")` parsed its "+" as a unary plus."""
        r = run_source(head("""
string s = (close >= 0 ? "+" : "-") + "x"
plot(str.length(s), title="n")
"""), BARS)
        self.assertEqual(2, r.last("n"))

    def test_scientific_notation_without_a_decimal_point(self):
        """Regression. `1e-10` lexed as `1`, `e`, `-10`."""
        r = run_source(head('plot(1e-10 * 1e10, title="v")'), BARS)
        self.assertAlmostEqual(1.0, r.last("v"))

    def test_multi_line_function_body_is_not_glued_to_its_header(self):
        """Regression. `=>` ends with `>`, which is a continuation token, so
        suffix matching joined every function header to its first body line."""
        r = run_source(head("""
add3(float a, float b, float c) =>
    float partial = a + b
    partial + c
plot(add3(1, 2, 3), title="v")
"""), BARS)
        self.assertEqual(6, r.last("v"))

    def test_generic_type_arguments_are_not_comparisons(self):
        r = run_source(head("""
var array<float> a = array.new<float>(3, 1.5)
plot(array.size(a), title="n")
plot(array.get(a, 0), title="v")
"""), BARS)
        self.assertEqual(3, r.last("n"))
        self.assertAlmostEqual(1.5, r.last("v"))

    def test_wrapped_boolean_expression_is_joined(self):
        r = run_source(head("""
bool flag = close > 0 and
     high > 0 and
     low > 0
plot(flag ? 1 : 0, title="f")
"""), BARS)
        self.assertEqual(1, r.last("f"))


class TestHonesty(unittest.TestCase):
    def test_an_unknown_builtin_raises_rather_than_returning_na(self):
        """A value invented here would travel silently into every result."""
        with self.assertRaises(PineRuntimeError) as ctx:
            run_source(head('plot(ta.supertrend(3, 10), title="v")'), BARS)
        self.assertIn("supertrend", str(ctx.exception))

    def test_assigning_to_an_undeclared_name_raises(self):
        with self.assertRaises(PineRuntimeError) as ctx:
            run_source(head("undeclared := 1\nplot(close, title='c')"), BARS)
        self.assertIn("undeclared", str(ctx.exception))

    def test_approximations_are_reported(self):
        r = run_source(head("""
float htf = request.security(syminfo.tickerid, "60", close)
plot(htf, title="h")
"""), BARS)
        self.assertTrue(any("request.security" in a for a in r.approximations))

    def test_a_syntax_error_names_its_line(self):
        with self.assertRaises(PineSyntaxError) as ctx:
            run_source(head("float x = )"), BARS)
        self.assertIsNotNone(ctx.exception.line)


class TestBuiltins(unittest.TestCase):
    def test_sma_matches_a_hand_calculation(self):
        r = run_source(head('plot(ta.sma(close, 10), title="v")'), BARS)
        expected = sum(b["close"] for b in BARS[-10:]) / 10
        self.assertAlmostEqual(expected, r.last("v"))

    def test_sma_is_na_until_the_window_fills(self):
        r = run_source(head('plot(ta.sma(close, 10), title="v")'), BARS)
        self.assertEqual(9, sum(1 for v in r.plot("v") if v is None))

    def test_two_call_sites_keep_separate_state(self):
        """Two ta.sma calls are two independent averages, as in Pine."""
        r = run_source(head("""
plot(ta.sma(close, 5), title="a")
plot(ta.sma(close, 20), title="b")
"""), BARS)
        self.assertNotAlmostEqual(r.last("a"), r.last("b"))

    def test_int_truncates_toward_zero(self):
        r = run_source(head("""
plot(int(2.9), title="a")
plot(int(-2.9), title="b")
"""), BARS)
        self.assertEqual(2, r.last("a"))
        self.assertEqual(-2, r.last("b"))

    def test_array_out_of_bounds_raises_with_the_index(self):
        with self.assertRaises(PineRuntimeError) as ctx:
            run_source(head("""
var array<float> a = array.new<float>(2, 0.0)
plot(array.get(a, 5), title="v")
"""), BARS)
        self.assertIn("out of bounds", str(ctx.exception))


class TestInputsAndSweeps(unittest.TestCase):
    SRC = """
int lengthInput = input.int(14, "Length", minval=1, maxval=200)
plot(ta.sma(close, lengthInput), title="v")
"""

    def test_default_is_used_when_no_override(self):
        r = run_source(head(self.SRC), BARS)
        self.assertAlmostEqual(sum(b["close"] for b in BARS[-14:]) / 14, r.last("v"))

    def test_an_override_changes_the_result(self):
        r = run_source(head(self.SRC), BARS, inputs={"Length": 5})
        self.assertAlmostEqual(sum(b["close"] for b in BARS[-5:]) / 5, r.last("v"))

    def test_overriding_an_unknown_title_is_silent_not_fatal(self):
        r = run_source(head(self.SRC), BARS, inputs={"Nope": 1})
        self.assertIsNotNone(r.last("v"))


class TestDrawingsAreCounted(unittest.TestCase):
    def test_boxes_created_in_a_loop_are_all_recorded(self):
        r = run_source(head("""
var array<box> pool = array.new<box>(0)
if barstate.islast
    for i = 0 to 9
        array.push(pool, box.new(bar_index, close, bar_index, close))
plot(array.size(pool), title="n")
"""), BARS)
        self.assertEqual(10, r.count_drawings("box"))
        self.assertEqual(10, r.last("n"))


PROJECT = REPO_ROOT / "indicators" / "swing_volume_profile" / "src" / "swing_volume_profile.pine"


@unittest.skipUnless(PROJECT.exists(), "private indicator not in this checkout")
class TestRealIndicator(unittest.TestCase):
    """The interpreter earns its keep here or nowhere.

    Skips rather than passes when the file is absent — it lives in an untracked
    directory, and a green tick for a check that never ran is the outcome this
    whole repo keeps trying to avoid."""

    @classmethod
    def setUpClass(cls):
        # 250 bars is enough for three or four swings to form, which is what
        # these invariants need. A tree-walking interpreter over a 1900-line
        # script costs real seconds per run, and a suite nobody waits for is a
        # suite nobody runs.
        cls.bars = synthetic_bars(250)
        cls.platform = Platform(mintick=0.01, timeframe="5")
        cls.result = run_file(str(PROJECT), cls.bars, platform=cls.platform)

    def test_it_runs_to_the_end(self):
        self.assertEqual(len(self.bars), self.result.bars)

    def test_volume_is_conserved_by_the_row_distribution(self):
        """Each bar's volume is spread across rows with a body weighting. The
        weights must still sum to exactly that bar's volume — otherwise the
        value-area target is computed against a total that does not exist."""
        for profile in self.result.global_value("swings").items:
            f = profile.fields
            spread = sum(f["buyRows"].items) + sum(f["sellRows"].items)
            self.assertAlmostEqual(f["totalVol"], spread, places=6)

    def test_marker_indices_are_inside_the_row_range(self):
        for profile in self.result.global_value("swings").items:
            f = profile.fields
            rows = len(f["buyRows"].items)
            for key in ("pocIdx", "maxBuyIdx", "maxSellIdx", "vaTopIdx", "vaBotIdx"):
                self.assertTrue(0 <= f[key] < rows, f"{key}={f[key]} rows={rows}")

    def test_the_value_area_brackets_the_poc(self):
        for profile in self.result.global_value("swings").items:
            f = profile.fields
            self.assertLessEqual(f["vaBotIdx"], f["pocIdx"])
            self.assertLessEqual(f["pocIdx"], f["vaTopIdx"])

    def test_the_box_budget_is_never_exceeded(self):
        self.assertLessEqual(self.result.global_value("boxesUsed"), 484)

    def test_no_swing_is_starved_when_the_budget_is_tight(self):
        """The bug this indicator shipped: a greedy pool gave the newest swing
        everything and left older ones with nothing. Every swing must now get a
        share at any row count."""
        for rows in (100, 400):
            with self.subTest(rows=rows):
                r = run_file(str(PROJECT), self.bars, platform=self.platform,
                             inputs={"Price Rows Per Swing": rows})
                grants = r.global_value("rowGrant").items
                self.assertTrue(grants)
                self.assertNotIn(0, grants, "a swing was allocated no boxes at all")

    def span_coverage(self, result):
        """How much of each swing's price range actually has bars drawn."""
        swings = list(result.global_value("swings").items)
        live = result.global_value("liveSwing")
        seq = ([live] if live is not None else []) + list(reversed(swings))
        ys = [d.props["lefttop"][1] for d in result.drawings
              if d.kind == "box" and isinstance(d.props.get("lefttop"), (list, tuple))]
        ys = [y for y in ys if isinstance(y, (int, float))]
        out = []
        for p in seq:
            f = p.fields
            lo, step, rows = f["lo"], f["step"], len(f["buyRows"].items)
            top = lo + rows * step
            inside = [y for y in ys if lo - 1e-9 <= y <= top + 1e-9]
            out.append(0.0 if not inside else (max(inside) - lo) / (top - lo) * 100)
        return out

    def test_every_profile_spans_its_whole_price_range(self):
        """The bug the user saw as "bars are there in some places and not in
        others". Rows run from the lowest price upward, and the drawing loop
        used to stop when the budget ran out — which deleted the TOP of every
        profile. Measured at 62.8% of the span on one swing.

        Rows are merged into wider bars now, so coverage must be total at every
        row count, however tight the budget."""
        for rows in (30, 100, 500):
            with self.subTest(rows=rows):
                r = run_file(str(PROJECT), self.bars, platform=self.platform,
                             inputs={"Price Rows Per Swing": rows})
                for i, pct in enumerate(self.span_coverage(r)):
                    self.assertGreater(pct, 99.0,
                                       f"swing {i} covers only {pct:.1f}% of its span")

    def test_whole_chart_mode_stays_inside_tradingview_limits(self):
        """Every swing on the chart, and still under 500 boxes, 500 lines and
        500 labels — crossing any of those drops the oldest drawings silently."""
        r = run_file(str(PROJECT), synthetic_bars(600), platform=self.platform,
                     inputs={"Cover The Whole Chart": True, "Price Rows Per Swing": 60})
        self.assertGreater(len(r.global_value("swings").items), 6,
                           "whole-chart mode kept no more swings than the default")
        for kind in ("box", "line", "label"):
            with self.subTest(kind=kind):
                self.assertLessEqual(r.count_drawings(kind), 500)

    def test_whole_chart_mode_still_covers_every_span(self):
        r = run_file(str(PROJECT), synthetic_bars(600), platform=self.platform,
                     inputs={"Cover The Whole Chart": True, "Price Rows Per Swing": 60})
        for i, pct in enumerate(self.span_coverage(r)):
            self.assertGreater(pct, 99.0,
                               f"swing {i} covers only {pct:.1f}% of its span")

    def test_thinning_only_happens_when_the_budget_is_spent(self):
        for rows in (30, 400):
            with self.subTest(rows=rows):
                r = run_file(str(PROJECT), self.bars, platform=self.platform,
                             inputs={"Price Rows Per Swing": rows})
                if r.global_value("thinnedSwings"):
                    self.assertLess(r.global_value("boxesSpare"), 2)


class TestTheShippedTemplateRuns(unittest.TestCase):
    """The template is what every new project starts from. If it lints clean
    and cannot execute, every project inherits that."""

    def test_a_scaffolded_indicator_executes(self):
        import json
        import tempfile
        from tests.helpers import run_script
        with tempfile.TemporaryDirectory() as td:
            proc = run_script("scaffold_project.py", "--kind", "indicator",
                              "--name", "interp_demo", "--out", td)
            self.assertEqual(0, proc.returncode, proc.stderr)
            src = Path(td) / "interp_demo" / "src" / "interp_demo.pine"
            result = run_file(str(src), synthetic_bars(150))
            self.assertEqual(150, result.bars)
            self.assertTrue(result.plots, "the template produced no plot at all")


if __name__ == "__main__":
    unittest.main()
