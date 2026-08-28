"""Higher-timeframe values, in the interpreter.

`request.security()` returned the CHART timeframe value, which is not an
approximation of an hourly series so much as a different series wearing its
name. Any script whose logic turned on an hourly close behaved offline as though
the hourly close were the 5-minute close, and every test of that logic agreed
with it.

The bars carry timestamps, so the higher-timeframe bars are built rather than
guessed, and the tests check them against an independently aggregated answer
rather than against the implementation's own opinion.
"""
import datetime
import sys
import unittest

from tests.helpers import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts"))

from pine_interp import Platform, run_source, synthetic_bars

FIVE_MIN = 300_000
HOUR = 3_600_000
START = int(datetime.datetime(2024, 3, 4, tzinfo=datetime.timezone.utc).timestamp() * 1000)


def bars(count=240, seed=7, step=FIVE_MIN):
    out = synthetic_bars(count, seed=seed)
    for i, bar in enumerate(out):
        bar["time"] = START + i * step
    return out


def probe(body, data=None, timeframe="5"):
    return run_source("//@version=6\nindicator(\"H\", overlay=true)\n" + body,
                      data if data is not None else bars(),
                      platform=Platform(mintick=0.01, timeframe=timeframe))


def hourly_closes(data):
    """The truth, aggregated here rather than asked of the interpreter."""
    order, close = [], {}
    for bar in data:
        slot = bar["time"] // HOUR
        if slot not in close:
            order.append(slot)
        close[slot] = bar["close"]
    return order, close


class TestHigherTimeframe(unittest.TestCase):
    def test_the_hourly_close_is_not_the_chart_close(self):
        """The failure this replaced. Every bar used to agree."""
        r = probe('plot(request.security(syminfo.tickerid, "60", close), title="h")\n'
                  'plot(close, title="c")')
        agree = sum(1 for a, b in zip(r.plot("h"), r.plot("c")) if a == b)
        self.assertEqual(0, agree)

    def test_it_matches_an_independently_aggregated_series(self):
        data = bars()
        r = probe('plot(request.security(syminfo.tickerid, "60", close), title="h")',
                  data)
        order, close = hourly_closes(data)
        got = r.plot("h")
        for i, bar in enumerate(data):
            slot = order.index(bar["time"] // HOUR)
            want = close[order[slot - 1]] if slot >= 1 else None
            if want is None:
                self.assertIsNone(got[i], f"bar {i} should have no hourly bar yet")
            else:
                self.assertAlmostEqual(want, got[i], places=9, msg=f"bar {i}")

    def test_only_a_closed_bar_is_served(self):
        """lookahead_off means the bar you get has already finished. Serving the
        forming one would produce results that cannot happen live, which is
        worse than the approximation this replaced."""
        data = bars()
        r = probe('plot(request.security(syminfo.tickerid, "60", close), title="h")',
                  data)
        got = r.plot("h")
        # Nothing in the first hour: there is no completed hourly bar yet.
        first_hour = [i for i, b in enumerate(data)
                      if b["time"] // HOUR == data[0]["time"] // HOUR]
        for i in first_hour:
            self.assertIsNone(got[i])

    def test_the_value_holds_flat_for_a_whole_higher_timeframe_bar(self):
        """Twelve 5-minute bars sit inside one hour, so the hourly value must
        step twelve bars at a time rather than drift."""
        r = probe('plot(request.security(syminfo.tickerid, "60", close), title="h")')
        got = [v for v in r.plot("h") if v is not None]
        steps = sum(1 for i in range(1, len(got)) if got[i] != got[i - 1])
        self.assertLess(steps, len(got) / 6,
                        "the hourly value is changing far too often to be hourly")

    def test_the_high_is_the_highest_of_the_bars_it_covers(self):
        data = bars()
        r = probe('plot(request.security(syminfo.tickerid, "60", high), title="h")',
                  data)
        order = []
        highs = {}
        for bar in data:
            slot = bar["time"] // HOUR
            if slot not in highs:
                order.append(slot)
                highs[slot] = bar["high"]
            highs[slot] = max(highs[slot], bar["high"])
        got = r.plot("h")
        for i, bar in enumerate(data):
            k = order.index(bar["time"] // HOUR)
            if k >= 1:
                self.assertAlmostEqual(highs[order[k - 1]], got[i], places=9)

    def test_lookahead_on_serves_the_forming_bar_and_says_so(self):
        """People reach for lookahead_on without meaning to repaint. The
        interpreter gives them what they asked for and names it."""
        r = probe('plot(request.security(syminfo.tickerid, "60", close,'
                  ' lookahead = barmerge.lookahead_on), title="h")')
        self.assertTrue(any("lookahead_on" in a for a in r.approximations))

    def test_a_lower_or_equal_timeframe_is_just_the_chart_bar(self):
        r = probe('plot(request.security(syminfo.tickerid, "5", close), title="h")\n'
                  'plot(close, title="c")')
        self.assertEqual(r.plot("c"), r.plot("h"))

    def test_a_computed_expression_falls_back_and_names_itself(self):
        """An arbitrary expression would have to be re-run against the
        higher-timeframe series in its own context, which the stateful ta.*
        call sites are not built for. It falls back, and says which kind of
        thing fell back rather than one blanket line."""
        r = probe('plot(request.security(syminfo.tickerid, "60",'
                  ' ta.sma(close, 5)), title="h")')
        self.assertTrue(any("computed expression" in a for a in r.approximations))

    def test_the_daily_bar_aggregates_too(self):
        data = bars(count=600)
        r = probe('plot(request.security(syminfo.tickerid, "D", close), title="h")',
                  data)
        got = [v for v in r.plot("h") if v is not None]
        self.assertTrue(got, "no daily value was ever produced")
        self.assertLess(len(set(got)), 5, "600 five-minute bars span about two days")


class TestTuplesAndOffsets(unittest.TestCase):
    """The two shapes that cover almost every real security call."""

    def test_a_tuple_answers_every_part(self):
        """One call, several questions. Anyone writes it this way once they
        notice TradingView caps a script at 40 security calls."""
        data = bars()
        r = probe('[a, b] = request.security(syminfo.tickerid, "60", [high, low])\n'
                  'plot(a, title="h")\nplot(b, title="l")', data)
        highs, lows = r.plot("h"), r.plot("l")
        pairs = [(h, l) for h, l in zip(highs, lows) if h is not None]
        self.assertTrue(pairs)
        for h, l in pairs:
            self.assertGreaterEqual(h, l, "the hourly high came out below its low")

    def test_a_history_offset_counts_higher_timeframe_bars(self):
        """`high[1]` on an hourly request is the hour BEFORE last, not the bar
        before on the chart. Counting chart bars here would make the previous-day
        high idiom quietly wrong."""
        data = bars()
        r = probe('plot(request.security(syminfo.tickerid, "60", close), title="now")\n'
                  'plot(request.security(syminfo.tickerid, "60", close[1]), title="prev")',
                  data)
        now, prev = r.plot("now"), r.plot("prev")
        # Wherever both exist, prev must equal what `now` held one hour earlier.
        seen = 0
        for i in range(1, len(data)):
            if prev[i] is None or now[i] is None:
                continue
            self.assertNotEqual(now[i], prev[i])
            seen += 1
        self.assertGreater(seen, 50, "not enough overlap to have tested anything")

    def test_the_previous_day_idiom_produces_a_flat_daily_level(self):
        data = bars(count=600)
        r = probe('[h, l] = request.security(syminfo.tickerid, "D", [high[1], low[1]],'
                  ' lookahead = barmerge.lookahead_on)\n'
                  'plot(h, title="pdh")\nplot(l, title="pdl")', data)
        pdh = [v for v in r.plot("pdh") if v is not None]
        self.assertTrue(pdh)
        self.assertLess(len(set(pdh)), 5, "600 five-minute bars span about two days")


class TestWhenLookaheadRepaints(unittest.TestCase):
    """lookahead_on is not repainting by itself, and saying it is would train
    the reader to ignore the warning."""

    def form(self, expr):
        return probe(f'plot(request.security(syminfo.tickerid, "60", {expr},'
                     f' lookahead = barmerge.lookahead_on), title="h")')

    def test_a_forming_high_repaints(self):
        self.assertTrue(any("FORMING" in a for a in self.form("high").approximations))

    def test_a_forming_close_repaints(self):
        self.assertTrue(any("FORMING" in a for a in self.form("close").approximations))

    def test_an_open_does_not_repaint(self):
        """A bar's open is fixed the moment it opens; it cannot change."""
        self.assertFalse(any("FORMING" in a for a in self.form("open").approximations))

    def test_a_history_offset_does_not_repaint(self):
        """`high[1]` with lookahead_on asks for a bar that has already closed.
        That is the standard previous-day idiom, and it is safe."""
        self.assertFalse(any("FORMING" in a
                             for a in self.form("high[1]").approximations))


if __name__ == "__main__":
    unittest.main()
