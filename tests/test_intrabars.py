"""Synthetic intrabars, and the two builtins that stopped guessing with them.

`request.security_lower_tf()` returns empty arrays offline by default, and that
stays the default: there is no sub-bar data, and inventing values would produce
a volume profile that looks measured and is fabricated.

What that cost was the CODE. swing_volume_profile's intrabar branch had never
executed once, and volume_pro's cumulative delta read zero for entire runs
because everything it depended on was empty. An untested branch is worse than an
approximate number, because the number announces itself.

So the synthesis is opt-in, and it guarantees the two properties that make it
defensible rather than decorative: the sub-bars span exactly the chart bar's own
high and low, and their volumes sum exactly to its volume.
"""
import datetime
import sys
import unittest

from tests.helpers import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts"))

from pine_interp import Platform, run_source, synthetic_bars

HOUR = 3_600_000
START = int(datetime.datetime(2024, 3, 4, tzinfo=datetime.timezone.utc).timestamp() * 1000)


def bars(count=120, seed=7):
    out = synthetic_bars(count, seed=seed)
    for i, bar in enumerate(out):
        bar["time"] = START + i * 300_000
    return out


def probe(body, intrabars=0, data=None):
    return run_source("//@version=6\nindicator(\"I\", overlay=true)\n" + body,
                      data if data is not None else bars(),
                      platform=Platform(mintick=0.01, timeframe="5",
                                        intrabars=intrabars))


HEAD = ('[h, l, c, v] = request.security_lower_tf(syminfo.tickerid, "1",'
        ' [high, low, close, volume])\n')


class TestSyntheticIntrabars(unittest.TestCase):
    def test_off_by_default_so_nothing_silently_changed(self):
        r = probe(HEAD + 'plot(array.size(v), title="n")')
        self.assertEqual(0, r.last("n"))
        self.assertTrue(any("returned na" in a for a in r.approximations))

    def test_it_produces_the_number_of_sub_bars_asked_for(self):
        r = probe(HEAD + 'plot(array.size(v), title="n")', intrabars=4)
        self.assertEqual(4, r.last("n"))

    def test_the_volumes_sum_to_the_bar_volume(self):
        """Nothing created, nothing lost. A profile built from sub-bars that do
        not add up would report a total the chart never traded."""
        r = probe(HEAD + 'plot(array.sum(v) - volume, title="d")', intrabars=5)
        for value in r.plot("d"):
            if value is not None:
                self.assertAlmostEqual(0.0, value, places=6)

    def test_the_sub_bars_span_the_bars_own_high_and_low(self):
        """A sub-bar series that never reaches the high would put volume where
        the chart says none traded."""
        r = probe(HEAD +
                  'plot(array.max(h) - high, title="dh")\n'
                  'plot(array.min(l) - low, title="dl")', intrabars=6)
        for key in ("dh", "dl"):
            for value in r.plot(key):
                if value is not None:
                    self.assertAlmostEqual(0.0, value, places=9, msg=key)

    def test_the_last_sub_bar_closes_where_the_bar_closed(self):
        r = probe(HEAD +
                  'plot(array.get(c, array.size(c) - 1) - close, title="d")',
                  intrabars=3)
        for value in r.plot("d"):
            if value is not None:
                self.assertAlmostEqual(0.0, value, places=9)

    def test_the_run_says_the_values_are_invented(self):
        """Anything measured from these describes the synthesis, not a market,
        and the report has to say so without being asked."""
        r = probe(HEAD + 'plot(array.size(v), title="n")', intrabars=4)
        self.assertTrue(any("SYNTHETIC" in a for a in r.approximations))
        self.assertFalse(any("returned na" in a for a in r.approximations))

    def test_a_single_sub_bar_is_the_bar_itself(self):
        r = probe(HEAD +
                  'plot(array.get(h, 0) - high, title="dh")\n'
                  'plot(array.get(l, 0) - low, title="dl")', intrabars=1)
        for key in ("dh", "dl"):
            for value in r.plot(key):
                if value is not None:
                    self.assertAlmostEqual(0.0, value, places=9, msg=key)


class TestTimeframeChange(unittest.TestCase):
    """It used to return false unconditionally, so a script gated on a
    higher-timeframe boundary took its 'nothing new' path for the whole run and
    the branch never executed at all."""

    def test_it_fires_once_per_higher_timeframe_bar(self):
        data = bars(count=300)
        r = probe('plot(timeframe.change("60") ? 1 : 0, title="c")', data=data)
        fired = int(sum(r.plot("c")))
        hours = len({b["time"] // HOUR for b in data})
        self.assertEqual(hours, fired)

    def test_it_does_not_fire_on_every_bar(self):
        r = probe('plot(timeframe.change("60") ? 1 : 0, title="c")')
        fired = int(sum(r.plot("c")))
        self.assertGreater(fired, 0, "it never fired, which was the old bug")
        self.assertLess(fired, 120 / 4, "it is firing far too often to be hourly")


class TestTimestampTimezone(unittest.TestCase):
    """A date built in Tokyo and one built in New York are different instants.
    Treating them as the same made every date window silently wrong."""

    def test_zones_produce_different_instants(self):
        r = probe('plot(timestamp("America/New_York", 2024, 3, 4, 0, 0), title="ny")\n'
                  'plot(timestamp("Asia/Tokyo", 2024, 3, 4, 0, 0), title="tk")\n'
                  'plot(timestamp("UTC", 2024, 3, 4, 0, 0), title="ut")')
        ny, tk, ut = r.last("ny"), r.last("tk"), r.last("ut")
        self.assertEqual(5, round((ny - ut) / HOUR), "New York is UTC-5 in March")
        self.assertEqual(-9, round((tk - ut) / HOUR), "Tokyo is UTC+9")

    def test_an_unknown_zone_falls_back_and_says_so(self):
        r = probe('plot(timestamp("Mars/Olympus", 2024, 3, 4, 0, 0), title="t")')
        self.assertTrue(any("does not know" in a for a in r.approximations))


if __name__ == "__main__":
    unittest.main()
