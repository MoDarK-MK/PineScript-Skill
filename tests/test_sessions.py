"""Sessions, in the interpreter.

`time(timeframe, session, timezone)` used to return na, so every session-based
script ran with all its phases switched off and could not be checked offline at
all. The bars carry real timestamps, so there was nothing to invent - only to
compare against.

The daylight-saving test is the one that earns its place. A fixed offset like
"UTC-5" is right for New York in winter and an hour wrong from March to
November, which moves every session boundary by twelve bars on a 5-minute chart.
That is the defect this file exists to be able to demonstrate.
"""
import datetime
import sys
import unittest

from tests.helpers import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts"))

from pine_interp import run_source, synthetic_bars

FIVE_MIN = 300_000


def at(year, month, day, count=600, seed=7):
    """Synthetic bars restamped onto a real date, five minutes apart."""
    start = int(datetime.datetime(year, month, day, 0, 0,
                                  tzinfo=datetime.timezone.utc).timestamp() * 1000)
    bars = synthetic_bars(count, seed=seed)
    for i, bar in enumerate(bars):
        bar["time"] = start + i * FIVE_MIN
    return bars


def probe(body, bars):
    return run_source("//@version=6\nindicator(\"S\", overlay=true)\n" + body, bars)


class TestSessionMembership(unittest.TestCase):
    def test_a_session_covers_the_hours_it_names(self):
        """Six hours a day of five-minute bars is 72 bars a day. Two days of
        bars should therefore land near 144, not near zero and not near all."""
        r = probe('plot(na(time(timeframe.period, "0000-0600", "UTC")) ? 0 : 1,'
                  ' title="s")', at(2024, 3, 4))
        inside = int(sum(r.plot("s")))
        self.assertGreater(inside, 100)
        self.assertLess(inside, 200)

    def test_a_session_that_wraps_midnight_is_understood(self):
        """2000-0200 is six hours spanning midnight, not a negative window."""
        r = probe('plot(na(time(timeframe.period, "2000-0200", "UTC")) ? 0 : 1,'
                  ' title="s")', at(2024, 3, 4))
        self.assertGreater(int(sum(r.plot("s"))), 100)

    def test_a_day_mask_removes_the_days_it_excludes(self):
        """Pine numbers weekdays from 1 = Sunday, which is not Python's
        numbering — an off-by-one here shifts the whole mask by a day."""
        full = probe('plot(na(time(timeframe.period, "0000-2359", "UTC")) ? 0 : 1,'
                     ' title="s")', at(2024, 3, 8, count=900))
        weekdays = probe('plot(na(time(timeframe.period, "0000-2359:23456", "UTC"))'
                         ' ? 0 : 1, title="s")', at(2024, 3, 8, count=900))
        self.assertGreater(int(sum(full.plot("s"))), int(sum(weekdays.plot("s"))))

    def test_no_session_argument_still_returns_the_bar_time(self):
        r = probe('plot(time, title="t")', at(2024, 3, 4, count=10))
        self.assertGreater(r.last("t"), 0)

    def test_an_unparseable_session_says_so_rather_than_guessing(self):
        r = probe('plot(na(time(timeframe.period, "nonsense", "UTC")) ? 0 : 1,'
                  ' title="s")', at(2024, 3, 4, count=20))
        self.assertEqual(0, int(sum(r.plot("s"))))
        self.assertTrue(any("could not be parsed" in a for a in r.approximations))


class TestDaylightSaving(unittest.TestCase):
    """The reason named zones matter, demonstrated rather than asserted."""

    BODY = ('bool fixed = not na(time(timeframe.period, "0600-0900", "UTC-5"))\n'
            'bool named = not na(time(timeframe.period, "0600-0900", "America/New_York"))\n'
            'plot(fixed != named ? 1 : 0, title="differ")\n')

    def test_a_fixed_offset_matches_the_named_zone_in_winter(self):
        r = probe(self.BODY, at(2024, 1, 8))
        self.assertEqual(0, int(sum(r.plot("differ"))),
                         "New York is UTC-5 in January; these should agree")

    def test_a_fixed_offset_is_an_hour_wrong_in_summer(self):
        """New York runs on UTC-4 from March to November. Pinning a session to
        UTC-5 moves every boundary by an hour for two thirds of the year."""
        r = probe(self.BODY, at(2024, 7, 8))
        differ = int(sum(r.plot("differ")))
        self.assertGreater(differ, 0,
                           "the whole point of naming a zone is that it carries "
                           "its own DST rule")
        # One hour either side of a two-boundary window, over two days.
        self.assertGreater(differ, 24)

    def test_an_unknown_zone_falls_back_and_says_so(self):
        r = probe('plot(na(time(timeframe.period, "0000-0600", "Mars/Olympus"))'
                  ' ? 0 : 1, title="s")', at(2024, 3, 4, count=20))
        self.assertTrue(any("not a zone this machine knows" in a
                            for a in r.approximations))


if __name__ == "__main__":
    unittest.main()
