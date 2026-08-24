"""
pine_interp — a Pine Script subset interpreter that runs offline.

The gap it closes: nothing in this repo could EXECUTE a Pine script. Fifty-six
lint rules match patterns; none of them run the code. Every claim about what an
indicator computes stayed unverified until it was pasted into TradingView, and
the bugs that reached a chart were logic bugs, not syntax ones — a budget
handed out greedily, a guard that never matched, a loop that counted down.

What it does:
    - executes a script bar by bar over OHLCV data
    - keeps real series history, so `close[1]` and `myVar[2]` mean what they mean
    - honours `var` (initialise once) versus a plain declaration (every bar)
    - supports user functions, UDTs, arrays, if/for/while/switch as expressions
    - returns inputs from an override map, so one file runs under many settings
    - records drawings instead of rendering them, so a test can count them

What it does NOT do, stated plainly because a partial interpreter that hides
its edges is worse than none:
    - CONFIRMED BARS ONLY. One pass per bar, no intrabar ticks, so a bug that
      only appears on a realtime tick cannot be reproduced here.
    - No `request.*`. Higher-timeframe and intrabar data have no source offline.
    - An unimplemented builtin RAISES rather than returning na. A value invented
      here would travel silently into every result downstream.

Usage:
    from pine_interp import run_file, synthetic_bars
    result = run_file("path/to/script.pine", synthetic_bars(300))
    result.plot("SMA")[-1]
"""
from .engine import Interpreter
from .platform import Platform
from .runtime import NA, Drawing, PineArray, PineRuntimeError, UDTInstance, is_na
from .syntax import PineSyntaxError, parse

__all__ = [
    "Interpreter", "Platform", "Result", "run_source", "run_file", "synthetic_bars",
    "bars_from_csv", "NA", "PineArray", "UDTInstance", "Drawing", "is_na",
    "PineSyntaxError", "PineRuntimeError", "parse",
]


class Result:
    """What a run produced, in the shapes a test wants to assert on."""

    def __init__(self, interp):
        self.interp = interp
        self.drawings = interp.drawings
        self.plots = interp.plots
        self.alerts = interp.alerts
        self.inputs = interp.inputs_seen
        self.bars = interp.bar_index + 1
        # Every place the run had to approximate. Printed with the result on
        # purpose: a number whose provenance is invisible invites more trust
        # than it has earned.
        self.approximations = sorted(interp.approximations)

    def plot(self, title):
        return self.plots.get(title, [])

    def last(self, title):
        values = self.plot(title)
        return values[-1] if values else None

    def global_value(self, name):
        """The final value of a global variable — how a test reaches inside."""
        series = self.interp.globals.lookup(name)
        return None if series is None else series.get(0)

    def global_history(self, name):
        series = self.interp.globals.lookup(name)
        return list(series.values) if series is not None else []

    def count_drawings(self, kind=None):
        if kind is None:
            return len(self.drawings)
        return sum(1 for d in self.drawings if d.kind == kind)

    def __repr__(self):
        return (f"<Result bars={self.bars} drawings={len(self.drawings)} "
                f"plots={list(self.plots)}>")


def run_source(source, bars, inputs=None, max_bars=None, platform=None):
    return Result(Interpreter(source, bars, inputs=inputs, max_bars=max_bars,
                              platform=platform).run())


def run_file(path, bars, inputs=None, max_bars=None, platform=None):
    with open(path, encoding="utf-8") as fh:
        return run_source(fh.read(), bars, inputs=inputs, max_bars=max_bars,
                          platform=platform)


def synthetic_bars(count, seed=7, start=100.0, volatility=1.0):
    """Deterministic pseudo-random OHLCV.

    Deterministic on purpose: a test that fails only sometimes teaches nothing,
    and a profile built from different bars each run cannot be compared against
    a stored expectation."""
    bars = []
    price = start
    state = seed
    for i in range(count):
        state = (1103515245 * state + 12345) % (1 << 31)
        drift = ((state >> 16) % 2000 - 1000) / 1000.0 * volatility
        state = (1103515245 * state + 12345) % (1 << 31)
        spread = ((state >> 16) % 1000) / 1000.0 * volatility + 0.1
        state = (1103515245 * state + 12345) % (1 << 31)
        vol = 100 + (state >> 16) % 900

        open_ = price
        close_ = max(0.01, price + drift)
        high_ = max(open_, close_) + spread
        low_ = max(0.01, min(open_, close_) - spread)
        bars.append({"open": open_, "high": high_, "low": low_, "close": close_,
                     "volume": float(vol), "time": 1_600_000_000_000 + i * 300_000})
        price = close_
    return bars


def bars_from_csv(path):
    """time,open,high,low,close,volume — the shape every exporter produces."""
    import csv
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            lower = {k.strip().lower(): v for k, v in row.items() if k}
            out.append({
                "time": int(float(lower.get("time") or lower.get("timestamp") or 0)),
                "open": float(lower["open"]),
                "high": float(lower["high"]),
                "low": float(lower["low"]),
                "close": float(lower["close"]),
                "volume": float(lower.get("volume") or 0),
            })
    return out
