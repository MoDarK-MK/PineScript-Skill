#!/usr/bin/env python3
"""
pine_run.py - Execute a Pine script offline and report what it computed.

The linter matches patterns. This RUNS the code, over real or synthetic bars,
and tells you what came out. It is the difference between "this looks like it
compiles" and "this produced 484 boxes, 3 swings, and a POC at 104.22".

Every run prints its approximations. Offline there is no intrabar data and no
higher-timeframe series, and a result that depended on either is not exact —
saying so beside the number is the only honest way to show it.

Usage:
    python3 scripts/pine_run.py FILE
    python3 scripts/pine_run.py FILE --bars 500
    python3 scripts/pine_run.py FILE --csv data.csv
    python3 scripts/pine_run.py FILE --set "Price Rows Per Swing=200"
    python3 scripts/pine_run.py FILE --var swings --var boxesUsed
    python3 scripts/pine_run.py FILE --sweep "Price Rows Per Swing=30,60,120"
    python3 scripts/pine_run.py FILE --json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pine_interp import (PineRuntimeError, PineSyntaxError, Platform,  # noqa: E402
                         bars_from_csv, run_file, synthetic_bars)
from pine_interp.runtime import PineArray, UDTInstance  # noqa: E402


def parse_setting(text):
    """`Title=value` — the value is read as JSON when it can be, else a string.

    JSON first because `30` should be a number and `true` a boolean; falling
    back to the raw text means a title like `Dark` still works."""
    if "=" not in text:
        raise SystemExit(f"--set needs Title=value, got {text!r}")
    key, _, raw = text.partition("=")
    try:
        return key.strip(), json.loads(raw)
    except json.JSONDecodeError:
        return key.strip(), raw


def describe(value, depth=0):
    if isinstance(value, PineArray):
        if not value.items:
            return "[] (empty)"
        head = value.items[:3]
        rendered = ", ".join(describe(v, depth + 1) for v in head)
        more = f", … {len(value.items) - 3} more" if len(value.items) > 3 else ""
        return f"[{rendered}{more}]  (size {len(value.items)})"
    if isinstance(value, UDTInstance):
        if depth > 1:
            return f"{value.type_name}(…)"
        inner = ", ".join(f"{k}={describe(v, depth + 1)}"
                          for k, v in list(value.fields.items())[:6])
        return f"{value.type_name}({inner}…)"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def load_bars(args):
    if args.csv:
        return bars_from_csv(args.csv)
    return synthetic_bars(args.bars, seed=args.seed)


def run_once(args, bars, overrides):
    return run_file(args.file, bars, inputs=overrides,
                    platform=Platform(mintick=args.mintick, timeframe=args.timeframe,
                                      intrabars=args.intrabars))


def main():
    parser = argparse.ArgumentParser(description="Run a Pine script offline.")
    parser.add_argument("file")
    parser.add_argument("--bars", type=int, default=300,
                        help="Synthetic bars to generate (default 300)")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--csv", help="Real OHLCV instead: time,open,high,low,close,volume")
    parser.add_argument("--set", action="append", default=[], metavar="TITLE=VALUE",
                        help="Override an input by its title. Repeatable.")
    parser.add_argument("--var", action="append", default=[], metavar="NAME",
                        help="Print a global variable's final value. Repeatable.")
    parser.add_argument("--sweep", metavar="TITLE=a,b,c",
                        help="Run once per value and compare the results")
    parser.add_argument("--intrabars", type=int, default=0,
                        help="Synthesise N sub-bars per chart bar for "
                             "request.security_lower_tf(), so the intrabar "
                             "code path can run. Values are invented; the "
                             "run says so.")
    parser.add_argument("--mintick", type=float, default=0.01)
    parser.add_argument("--timeframe", default="5")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

    bars = load_bars(args)
    overrides = dict(parse_setting(s) for s in args.set)

    try:
        if args.sweep:
            return run_sweep(args, bars, overrides)
        result = run_once(args, bars, overrides)
    except (PineSyntaxError, PineRuntimeError) as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1

    payload = {
        "file": args.file,
        "bars": result.bars,
        "drawings": {k: result.count_drawings(k)
                     for k in ("box", "line", "label", "table", "polyline")
                     if result.count_drawings(k)},
        "plots": {str(title): values[-1] for title, values in result.plots.items()},
        "alerts": len(result.alerts),
        "inputs_seen": len(result.inputs),
        "approximations": result.approximations,
        "variables": {name: describe(result.global_value(name)) for name in args.var},
    }

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
        return 0

    print(f"{args.file}")
    print(f"  bars run        {payload['bars']}")
    if payload["drawings"]:
        print("  drawings        " + ", ".join(f"{v} {k}" for k, v in
                                               payload["drawings"].items()))
    for title, value in payload["plots"].items():
        # str() first: a plot title can be a Namespace when the script passed a
        # constant rather than a literal, and Namespace has no __format__.
        print(f"  plot {str(title):<14} {describe(value)}")
    for name in args.var:
        print(f"  var  {name:<14} {payload['variables'][name]}")
    if payload["alerts"]:
        print(f"  alerts          {payload['alerts']}")
    if result.approximations:
        print()
        print("  APPROXIMATIONS — results depending on these are not exact:")
        for note in result.approximations:
            print(f"    - {note}")
    return 0


def run_sweep(args, bars, base_overrides):
    """One file, many settings — the offline parameter sweep.

    Possible only because input.*() reads from an override map instead of the
    source, so nothing has to be edited between runs."""
    title, _, values = args.sweep.partition("=")
    title = title.strip()
    if not values:
        raise SystemExit("--sweep needs TITLE=a,b,c")

    rows = []
    for raw in values.split(","):
        try:
            value = json.loads(raw.strip())
        except json.JSONDecodeError:
            value = raw.strip()
        overrides = dict(base_overrides)
        overrides[title] = value
        result = run_once(args, bars, overrides)
        rows.append({
            "value": value,
            "drawings": result.count_drawings(),
            "plots": {t: v[-1] for t, v in result.plots.items()},
            "variables": {n: describe(result.global_value(n)) for n in args.var},
        })

    if args.json:
        print(json.dumps({"input": title, "runs": rows}, indent=2, default=str))
        return 0

    print(f"{args.file} — sweeping {title!r} over {len(rows)} value(s)\n")
    headers = ["value", "drawings"] + args.var
    widths = [max(len(str(h)), 12) for h in headers]
    print("  ".join(str(h).ljust(w) for h, w in zip(headers, widths)))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        cells = [str(row["value"]), str(row["drawings"])] + \
                [row["variables"].get(n, "") for n in args.var]
        print("  ".join(str(c)[:w].ljust(w) for c, w in zip(cells, widths)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
