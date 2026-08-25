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


class TestPineArithmetic(unittest.TestCase):
    """Pine's arithmetic, not Python's.

    An interpreter that is more forgiving than the platform does not merely miss
    bugs, it vouches for them. This class exists because it did: a profile that
    was cut off on every chart passed every test here for weeks, because `30/14`
    came out 2.142 offline and 2 on TradingView."""

    def test_two_integers_divide_as_an_integer(self):
        r = run_source(head("plot(30 / 14, title=\"d\")"), BARS)
        self.assertEqual(2, r.last("d"))

    def test_rounding_an_integer_division_cannot_round_anything(self):
        """The exact shape of the bug that shipped."""
        r = run_source(head("plot(math.ceil(30 / 14), title=\"d\")"), BARS)
        self.assertEqual(2, r.last("d"))

    def test_truncation_is_toward_zero_not_floor(self):
        """Pine truncates like C. Python's // floors, which differs for
        negatives: -3 against -4."""
        r = run_source(head("plot(-7 / 2, title=\"d\")"), BARS)
        self.assertEqual(-3, r.last("d"))

    def test_one_float_operand_makes_it_float_division(self):
        r = run_source(head("plot(30 * 1.0 / 14, title=\"d\")"), BARS)
        self.assertAlmostEqual(30 / 14, r.last("d"), places=9)

    def test_a_float_declaration_keeps_its_type(self):
        """`float x = 3` holds 3.0, not 3 — otherwise dividing it would
        truncate and the fix for integer division would introduce the opposite
        bug in its place."""
        r = run_source(head("float x = 3\nplot(x / 2, title=\"d\")"), BARS)
        self.assertAlmostEqual(1.5, r.last("d"), places=9)

    def test_a_float_keeps_its_type_through_reassignment(self):
        r = run_source(head(
            "var array<float> a = array.new<float>(3, 1.0)\n"
            "float x = 0.0\n"
            "x := array.size(a)\n"
            "plot(x / 2, title=\"d\")"), BARS)
        self.assertAlmostEqual(1.5, r.last("d"), places=9)

    def test_an_int_declaration_truncates_what_it_is_given(self):
        r = run_source(head("int n = 7.9\nplot(n, title=\"d\")"), BARS)
        self.assertEqual(7, r.last("d"))


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

    def test_no_profile_reaches_into_the_next_swing(self):
        """0.9.0's Minimum Width floor gave every profile at least 20 chart bars
        whether or not the swing owned them, so a 5-bar swing was drawn across 20
        and covered the two swings after it. Overlapping profiles are worse than
        thin ones: a row lying across three swings describes none of them.

        The width rule is recomputed here rather than read back, because the
        boxes themselves cannot be grouped by swing — a split row's buy box
        starts partway along, so its left edge is not the profile's."""
        swings = list(self.result.global_value("swings").items)
        live = self.result.global_value("liveSwing")
        if live is not None:
            swings = swings + [live]
        self.assertGreater(len(swings), 1, "need two swings to overlap at all")

        max_pct = self.result.global_value("maxWidthPctInput")
        min_bars = self.result.global_value("minProfileBarsInput")
        last_bar = self.result.bars - 1

        for n, s in enumerate(swings):
            left, right = s.fields["leftBar"], s.fields["rightBar"]
            next_left = swings[n + 1].fields["leftBar"] if n + 1 < len(swings) else last_bar
            fitted = max(1, int(max(1, right - left) * max_pct / 100))
            room = max(1, int(max(1, next_left - left) * max_pct / 100))
            right_edge = left + min(max(fitted, min_bars), room)
            self.assertLessEqual(
                right_edge, next_left,
                f"swing {n} drawn {left}-{right_edge} but the next starts at {next_left}")

    def test_a_targets_hit_array_matches_its_target_count(self):
        """One flag per target. A shorter `hits` array would raise on the first
        rank past its end; a longer one would silently never be read."""
        for lv in self.result.global_value("tracked").items:
            self.assertEqual(len(lv.fields["targets"].items),
                             len(lv.fields["hits"].items))

    def test_the_three_stops_are_ordered_and_on_the_right_side(self):
        """Each tier has its own rule and they are NOT naturally ordered: the
        first shelf below an entry can sit under the value-area edge, which
        would leave "Tight" further out than "Balanced" and make both labels
        lie. The order is enforced after the fact, and this is what checks it.

        Also that no stop lands on the wrong side of its own entry, which the
        value-area rule can produce on its own when the entry is outside the
        value area."""
        checked = 0
        for lv in self.result.global_value("tracked").items:
            stops = list(lv.fields["stops"].items)
            if len(stops) != 3:
                continue
            checked += 1
            price, is_buy = lv.fields["price"], lv.fields["isBuy"]
            for tier, stop in enumerate(stops):
                if is_buy:
                    self.assertLess(stop, price, f"buy stop {tier} above its entry")
                else:
                    self.assertGreater(stop, price, f"sell stop {tier} below its entry")
            near, mid, far = (abs(price - s) for s in stops)
            self.assertLessEqual(near, mid + 1e-9, "Balanced is tighter than Tight")
            self.assertLessEqual(mid, far + 1e-9, "Wide is tighter than Balanced")
        if checked == 0:
            self.skipTest("no levels were tracked on this data")

    def test_stop_outcomes_never_exceed_the_windows_that_closed(self):
        """A level's stop is decided once, so hit and win are exclusive and
        neither can outrun the number of closed windows. Anything else means an
        outcome was recorded twice or a window was scored without closing."""
        hit = list(self.result.global_value("stopHitN").items)
        win = list(self.result.global_value("stopWinN").items)
        scored = list(self.result.global_value("stopScoredN").items)
        for tier, (h, w, s) in enumerate(zip(hit, win, scored)):
            self.assertLessEqual(h, s, f"tier {tier}: {h} hit of {s} scored")
            self.assertLessEqual(w, s, f"tier {tier}: {w} won of {s} scored")
            self.assertLessEqual(h + w, s,
                                 f"tier {tier}: {h} hit + {w} won exceeds {s} scored")

    def test_a_wider_stop_is_never_hit_more_often_in_the_same_window(self):
        """Not asserted as a global invariant, because it can legitimately fail:
        if the target arrives while only the tight stop has been passed, the
        tight stop is marked target-first and a later break can still stop the
        wide one out. What IS guaranteed is per level and per bar — a wide stop
        cannot be hit while the tight one in front of it is still open."""
        for lv in self.result.global_value("tracked").items:
            states = list(lv.fields["stopState"].items)
            if len(states) != 3:
                continue
            for near, far in zip(states, states[1:]):
                if far == 1:  # SL_STOPPED
                    self.assertNotEqual(0, near,
                                        "a wider stop was hit while the tighter "
                                        "one in front of it was still open")

    def test_no_stop_is_suggested_before_the_evidence_exists(self):
        """The 20-sample floor is a refusal, not a formality: under it the
        ranking is noise wearing a percentage sign. A short run cannot close 20
        windows, so nothing may claim to be proven."""
        r = run_file(str(PROJECT), synthetic_bars(120), platform=self.platform)
        self.assertFalse(r.global_value("stopProven"),
                         "a placement was called proven on 120 bars")
        scored = list(r.global_value("stopScoredN").items)
        self.assertTrue(all(s < 20 for s in scored),
                        f"120 bars closed 20+ windows: {scored}")

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

    def test_a_high_swing_count_stays_inside_tradingview_limits(self):
        """The swing count is uncapped now. Crossing 500 boxes, lines or labels
        drops the oldest drawings with no error at all, so the script has to
        stay under them by itself."""
        r = run_file(str(PROJECT), synthetic_bars(700), platform=self.platform,
                     inputs={"Swings To Show": 500, "Price Rows Per Swing": 60,
                             "Pivot Length": 5})
        self.assertGreater(len(r.global_value("swings").items), 6,
                           "a high swing count kept no more swings than the default")
        for kind in ("box", "line", "label"):
            with self.subTest(kind=kind):
                self.assertLessEqual(r.count_drawings(kind), 500)

    def test_a_high_swing_count_still_covers_every_span(self):
        r = run_file(str(PROJECT), synthetic_bars(700), platform=self.platform,
                     inputs={"Swings To Show": 500, "Price Rows Per Swing": 60,
                             "Pivot Length": 5})
        for i, pct in enumerate(self.span_coverage(r)):
            self.assertGreater(pct, 99.0,
                               f"swing {i} covers only {pct:.1f}% of its span")

    def test_the_entry_search_does_not_grow_with_the_swing_count(self):
        """The entry search is the ONE calculation that reruns on every price
        change, and it costs a pass over a swing's rows per swing. Unbounded, at
        500 swings of 500 rows that is a quarter of a million array reads
        between one tick and the next — so raising the swing limit without
        bounding this would stall the script at exactly the settings the raised
        limit exists for."""
        from pine_interp.engine import Interpreter
        source = PROJECT.read_text(encoding="utf-8")
        bars = synthetic_bars(700)

        def searches(swing_setting):
            interp = Interpreter(source, bars, platform=self.platform,
                                 inputs={"Swings To Show": swing_setting,
                                         "Price Rows Per Swing": 60,
                                         "Pivot Length": 5})
            seen = [0]
            original = interp.call_user

            def counting(name, pos, named, node):
                if name == "bestEntry":
                    seen[0] += 1
                return original(name, pos, named, node)

            interp.call_user = counting
            interp.run()
            kept = len(interp.globals.lookup("swings").get(0).items)
            return seen[0], kept

        few, few_kept = searches(10)
        many, many_kept = searches(500)
        self.assertGreater(many_kept, few_kept + 20,
                           "the two runs kept a similar number of swings, so this "
                           "proves nothing about the bound")
        # Each completed swing registers one level for the hit-rate tracker, so
        # the totals differ by that; what must NOT scale is the per-tick search.
        per_tick_few = few - few_kept
        per_tick_many = many - many_kept
        self.assertLessEqual(per_tick_many, per_tick_few + 20,
                             f"the per-tick entry search grew from {per_tick_few} "
                             f"to {per_tick_many} with the swing count")

    def test_a_profile_spends_all_the_room_it_is_allotted(self):
        """Row widths are normalised against the busiest bucket, so that bucket
        spans the profile's full width exactly and nothing is left unused.

        Checked in TIME, because that is what the boxes are positioned by now.
        Whole bar numbers capped a four-bar-wide profile at four distinct row
        lengths, which drew thirty-four rows as a solid block; milliseconds have
        no such limit. Coverage of the price span is asserted separately in
        test_every_profile_spans_its_whole_price_range."""
        r = run_file(str(PROJECT), synthetic_bars(700), platform=self.platform,
                     inputs={"Swings To Show": 8, "Pivot Length": 6,
                             "Minimum Width (bars)": 20})
        boxes = [d for d in r.drawings if d.kind == "box"
                 and isinstance(d.props.get("lefttop"), (list, tuple))
                 and isinstance(d.props.get("rightbottom"), (list, tuple))]
        self.assertTrue(boxes, "no row boxes were drawn at all")

        swings = list(r.global_value("swings").items)
        live = r.global_value("liveSwing")
        if live is not None:
            swings = swings + [live]
        max_pct = r.global_value("maxWidthPctInput")
        min_bars = r.global_value("minProfileBarsInput")
        last_bar = r.bars - 1
        checked = 0
        for n, s in enumerate(swings):
            left, right = s.fields["leftBar"], s.fields["rightBar"]
            nxt = swings[n + 1].fields["leftBar"] if n + 1 < len(swings) else last_bar
            fitted = max(1, int(max(1, right - left) * max_pct / 100))
            room = max(1, int(max(1, nxt - left) * max_pct / 100))
            right_edge = left + min(max(fitted, min_bars), room)
            left_time = s.fields["leftTime"]
            ms_per_bar = (s.fields["rightTime"] - left_time) / max(1, right - left)
            if ms_per_bar <= 0:
                continue
            want = left_time + (right_edge - left) * ms_per_bar
            mine = [b for b in boxes
                    if left_time - 1 <= b.props["lefttop"][0] <= want + 1]
            if not mine:
                continue
            checked += 1
            widest = max(b.props["rightbottom"][0] for b in mine)
            # Within one millisecond: the coordinates are integers, and the
            # busiest bucket is meant to reach the profile's right edge exactly.
            self.assertLessEqual(abs(widest - want), 1.0 + ms_per_bar * 0.001,
                                 f"swing {n} was given up to {want} but its "
                                 f"widest row reaches {widest}")
        self.assertGreater(checked, 0, "no profile could be matched to a swing")

    def test_a_narrow_profile_still_has_room_to_show_a_shape(self):
        """The failure this replaced a whole approach over. A profile four chart
        bars wide, positioned by bar index, had four row lengths available and
        drew thirty-four rows with them - a block with two steps in it, which is
        what the short swings looked like on the chart while the long ones
        looked fine.

        Widening the profile was the wrong answer and produced the overlap of
        0.10.0: the room in front of a short swing genuinely is four bars."""
        r = run_file(str(PROJECT), synthetic_bars(700), platform=self.platform,
                     inputs={"Swings To Show": 6, "Price Rows Per Swing": 200})
        swings = list(r.global_value("swings").items)
        live = r.global_value("liveSwing")
        if live is not None:
            swings = swings + [live]
        boxes = [d for d in r.drawings if d.kind == "box"
                 and isinstance(d.props.get("lefttop"), (list, tuple))]
        narrowest = None
        for n, s in enumerate(swings):
            span = s.fields["rightBar"] - s.fields["leftBar"]
            if narrowest is None or span < narrowest[1]:
                narrowest = (s, span)
        s = narrowest[0]
        left_time = s.fields["leftTime"]
        mine = [b for b in boxes if b.props["lefttop"][0] == left_time]
        if len(mine) < 8:
            self.skipTest("the narrowest swing drew too few rows to judge")
        lengths = {b.props["rightbottom"][0] - left_time for b in mine}
        # Whole bars gave four. Anything in single figures is the old bug back.
        self.assertGreater(len(lengths), 10,
                           f"the narrowest swing ({narrowest[1]} bars) drew "
                           f"{len(mine)} rows with only {len(lengths)} distinct "
                           f"lengths — the shape is quantised away")

    def test_every_target_is_further_out_than_the_one_before(self):
        """Spacing is applied between successive targets, not only from the
        entry. From the entry alone, ten targets come out of the same shelf a
        tick apart: ten lines drawn on top of each other, and ten reach rates
        that are all really the first one's."""
        r = run_file(str(PROJECT), synthetic_bars(900), platform=self.platform,
                     inputs={"Swings To Show": 8, "Pivot Length": 6,
                             "Minimum Target Distance (ATR)": 1.5})
        seen = 0
        for lv in r.global_value("tracked").items:
            targets = list(lv.fields["targets"].items)
            price = lv.fields["price"]
            for target in targets:
                self.assertNotEqual(target, price,
                                    "a target landed on its own entry price")
            if len(targets) < 2:
                continue
            seen += 1
            want = (sorted(targets) if lv.fields["isBuy"]
                    else sorted(targets, reverse=True))
            self.assertEqual(want, targets, f"targets out of order: {targets}")
            for earlier, later in zip(targets, targets[1:]):
                self.assertNotEqual(earlier, later, "two targets at one price")
        if seen == 0:
            self.skipTest("no level projected more than one target on this data")

    def test_no_target_rank_reports_more_than_100_percent(self):
        """The numerator moves when a target is reached and the denominator when
        its window closes. A level evicted before its window closed used to
        leave reaches counted with nothing beneath them, and that can only
        surface as a rate above 100% - the one arithmetic impossibility this
        statistic is able to produce."""
        r = run_file(str(PROJECT), synthetic_bars(900), platform=self.platform,
                     inputs={"Swings To Show": 8, "Pivot Length": 6})
        reached = list(r.global_value("targetReachedN").items)
        scored = list(r.global_value("targetScoredN").items)
        self.assertEqual(len(reached), len(scored))
        for rank, (hit, total) in enumerate(zip(reached, scored), start=1):
            self.assertGreaterEqual(hit, 0)
            self.assertLessEqual(hit, total, f"T{rank}: {hit} reached of {total} scored")

    def test_a_target_is_published_only_alongside_a_drawn_entry(self):
        """A projection for a level that is not on the chart would be a line
        pointing away from nothing."""
        r = run_file(str(PROJECT), synthetic_bars(700), platform=self.platform,
                     inputs={"Which Side": "Buy Side Only"})
        self.assertIsNone(r.global_value("targetSellPrice"),
                          "a sell target survived with the sell entry hidden")

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
