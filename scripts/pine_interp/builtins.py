"""
The builtin surface: math.*, ta.*, array.*, str.*, input.*, and the drawing
family.

Two rules govern what is here.

FIRST: an unknown builtin RAISES. It would be easy to return na for anything
unrecognised and let scripts "work", and that would make every result
untrustworthy — a profile built from na is still a profile-shaped object. If
the interpreter does not know a function, it says so and names it.

SECOND: drawing calls are recorded, never rendered. What a test wants from
box.new() is that it happened, how many times, and with what coordinates.
"""
import datetime
import math
import re
import zoneinfo

from .platform import timeframe_seconds
from .runtime import (NA, Drawing, PineArray, PineRuntimeError, UDTInstance,
                      format_number, is_na, num, nz, ta_ema, ta_extreme,
                      ta_pivot, ta_rma, ta_sma, truthy)

DRAWING_KINDS = ("box", "line", "label", "table", "polyline", "linefill")


def _f(v, default=NA):
    n = num(v)
    return default if is_na(n) else float(n)


def _i(v, default=0):
    n = num(v)
    return default if is_na(n) else int(n)


def dispatch(interp, path, pos, named, node, scope):
    fn = TABLE.get(path)
    if fn is not None:
        return fn(interp, pos, named, node)

    head = path.split(".", 1)[0]
    if head in DRAWING_KINDS:
        return _drawing(interp, path, pos, named, node)
    if path.startswith("input"):
        return _input(interp, path, pos, named, node)
    if head in ("color",):
        return _color(interp, path, pos, named, node)
    if head in ("plot", "plotshape", "plotchar", "plotarrow", "bgcolor",
                "barcolor", "fill", "hline", "alertcondition", "indicator",
                "strategy", "library"):
        return _output(interp, path, pos, named, node)

    raise PineRuntimeError(
        f"'{path}()' is not implemented by the interpreter. It returns nothing "
        f"rather than guessing — a value invented here would travel silently "
        f"into every result downstream.", node.line)


# --------------------------------------------------------------------- core
def _na(interp, pos, named, node):
    return is_na(pos[0]) if pos else True


def _nz(interp, pos, named, node):
    value = pos[0] if pos else NA
    fallback = pos[1] if len(pos) > 1 else 0
    return fallback if is_na(value) else value


def _tostring(interp, pos, named, node):
    value = pos[0] if pos else NA
    fmt = pos[1] if len(pos) > 1 else named.get("format")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, PineArray):
        return "[" + ", ".join(format_number(v, None) for v in value.items) + "]"
    return format_number(value, fmt)


def _tonumber(interp, pos, named, node):
    try:
        return float(pos[0])
    except (TypeError, ValueError):
        return NA


# --------------------------------------------------------------------- math
def _math1(fn):
    def call(interp, pos, named, node):
        v = _f(pos[0] if pos else NA)
        if is_na(v):
            return NA
        try:
            return fn(v)
        except ValueError:
            return NA
    return call


def _math_minmax(pick):
    def call(interp, pos, named, node):
        values = [num(v) for v in pos]
        if any(is_na(v) for v in values) or not values:
            return NA
        result = pick(values)
        # int in, int out. Pine preserves integer-ness here and code depends on
        # it: `int n = math.min(a, b)` will not compile against a float.
        if all(isinstance(v, int) and not isinstance(v, bool) for v in values):
            return int(result)
        return result
    return call


def _math_round(interp, pos, named, node):
    v = _f(pos[0] if pos else NA)
    if is_na(v):
        return NA
    digits = _i(pos[1], 0) if len(pos) > 1 else _i(named.get("precision"), 0)
    factor = 10 ** digits
    return math.floor(v * factor + 0.5) / factor


def _math_sum(interp, pos, named, node):
    raise PineRuntimeError("math.sum() is not implemented", node.line)


# ----------------------------------------------------------------------- ta
def _ta_sma(interp, pos, named, node):
    return ta_sma(interp.state_for(node), pos[0], pos[1])


def _ta_ema(interp, pos, named, node):
    return ta_ema(interp.state_for(node), pos[0], pos[1])


def _ta_rma(interp, pos, named, node):
    return ta_rma(interp.state_for(node), pos[0], pos[1])


def _ta_highest(interp, pos, named, node):
    src, length = (pos[0], pos[1]) if len(pos) > 1 else (interp.high, pos[0])
    return ta_extreme(interp.state_for(node), src, length, max)


def _ta_lowest(interp, pos, named, node):
    src, length = (pos[0], pos[1]) if len(pos) > 1 else (interp.low, pos[0])
    return ta_extreme(interp.state_for(node), src, length, min)


def _ta_tr(interp, pos, named, node):
    prev_close = interp.hist["close"][-2] if len(interp.hist["close"]) > 1 else NA
    hi, lo = _f(interp.high), _f(interp.low)
    if is_na(hi) or is_na(lo):
        return NA
    if is_na(prev_close):
        return hi - lo
    pc = _f(prev_close)
    return max(hi - lo, abs(hi - pc), abs(lo - pc))


def _ta_atr(interp, pos, named, node):
    tr = _ta_tr(interp, [], {}, node)
    return ta_rma(interp.state_for(node), tr, pos[0] if pos else 14)


def _ta_change(interp, pos, named, node):
    """Only `close`-style built-ins and plain variables have history here, and
    ta.change is called on those in practice."""
    st = interp.state_for(node)
    cur = num(pos[0] if pos else NA)
    prev = st.get("prev")
    st["prev"] = cur
    if is_na(cur) or prev is None or is_na(prev):
        return NA
    return cur - prev


def _ta_cum(interp, pos, named, node):
    st = interp.state_for(node)
    cur = num(pos[0] if pos else NA)
    st["total"] = nz(st.get("total"), 0) + (0 if is_na(cur) else cur)
    return st["total"]


def _ta_pivothigh(interp, pos, named, node):
    src, left, right = _pivot_args(interp, pos, named, True)
    return ta_pivot(src, src, left, right, True)


def _ta_pivotlow(interp, pos, named, node):
    src, left, right = _pivot_args(interp, pos, named, False)
    return ta_pivot(src, src, left, right, False)


def _pivot_args(interp, pos, named, want_high):
    if len(pos) >= 3:
        # ta.pivothigh(source, left, right) — the source must be a series we
        # keep history for, and in practice that is high/low.
        return (interp.hist["high"] if want_high else interp.hist["low"],
                pos[1], pos[2])
    return (interp.hist["high"] if want_high else interp.hist["low"],
            pos[0], pos[1])


def _ta_crossover(interp, pos, named, node):
    st = interp.state_for(node)
    a, b = num(pos[0]), num(pos[1])
    pa, pb = st.get("a"), st.get("b")
    st["a"], st["b"] = a, b
    if any(is_na(x) or x is None for x in (a, b, pa, pb)):
        return False
    return pa <= pb and a > b


def _ta_crossunder(interp, pos, named, node):
    st = interp.state_for(node)
    a, b = num(pos[0]), num(pos[1])
    pa, pb = st.get("a"), st.get("b")
    st["a"], st["b"] = a, b
    if any(is_na(x) or x is None for x in (a, b, pa, pb)):
        return False
    return pa >= pb and a < b


def _ta_cross(interp, pos, named, node):
    st = interp.state_for(node)
    a, b = num(pos[0]), num(pos[1])
    pa, pb = st.get("a"), st.get("b")
    st["a"], st["b"] = a, b
    if any(is_na(x) or x is None for x in (a, b, pa, pb)):
        return False
    return (pa <= pb and a > b) or (pa >= pb and a < b)


def _ta_stdev(interp, pos, named, node):
    length = _i(pos[1], 0) if len(pos) > 1 else 0
    v = num(pos[0]) if pos else NA
    if length <= 0 or is_na(v):
        return NA
    from .runtime import RollingWindow
    w = interp.state_for(node).setdefault("w", RollingWindow(length))
    w.length = length
    buf = w.push(float(v))
    if len(buf) < length:
        return NA
    window = buf[-length:]
    mean = sum(window) / length
    # Population, not sample — Pine's ta.stdev uses the biased estimator.
    return (sum((x - mean) ** 2 for x in window) / length) ** 0.5


def _ta_wma(interp, pos, named, node):
    length = _i(pos[1], 0) if len(pos) > 1 else 0
    v = num(pos[0]) if pos else NA
    if length <= 0 or is_na(v):
        return NA
    from .runtime import RollingWindow
    w = interp.state_for(node).setdefault("w", RollingWindow(length))
    w.length = length
    buf = w.push(float(v))
    if len(buf) < length:
        return NA
    window = buf[-length:]
    weights = range(1, length + 1)
    return sum(x * k for x, k in zip(window, weights)) / sum(weights)


def _ta_rsi(interp, pos, named, node):
    """Wilder's RSI, built on the same rma this file already provides so the
    two cannot drift apart."""
    st = interp.state_for(node)
    v = num(pos[0]) if pos else NA
    length = _i(pos[1], 14) if len(pos) > 1 else 14
    prev = st.get("prev")
    st["prev"] = v
    if is_na(v) or prev is None or is_na(prev):
        return NA
    gain = max(v - prev, 0.0)
    loss = max(prev - v, 0.0)
    up = ta_rma(st.setdefault("up", {}), gain, length)
    down = ta_rma(st.setdefault("down", {}), loss, length)
    if is_na(up) or is_na(down):
        return NA
    if down == 0:
        return 100.0
    if up == 0:
        return 0.0
    return 100.0 - 100.0 / (1.0 + up / down)


def _ta_barssince(interp, pos, named, node):
    st = interp.state_for(node)
    if truthy(pos[0] if pos else False):
        st["n"] = 0
    elif "n" in st:
        st["n"] += 1
    else:
        return NA
    return st["n"]


def _ta_valuewhen(interp, pos, named, node):
    st = interp.state_for(node)
    hist = st.setdefault("hits", [])
    if truthy(pos[0]):
        hist.append(pos[1])
    occurrence = _i(pos[2], 0) if len(pos) > 2 else 0
    idx = len(hist) - 1 - occurrence
    return hist[idx] if 0 <= idx < len(hist) else NA


# -------------------------------------------------------------------- array
def _arr(v, node, what="array"):
    if not isinstance(v, PineArray):
        raise PineRuntimeError(f"expected an {what}, got {type(v).__name__}",
                               node.line)
    return v


def _array_new(interp, pos, named, node):
    size = _i(pos[0], 0) if pos else _i(named.get("size"), 0)
    initial = pos[1] if len(pos) > 1 else named.get("initial_value", NA)
    return PineArray([initial] * size)


def _array_get(interp, pos, named, node):
    a = _arr(pos[0], node)
    i = _i(pos[1])
    if i < 0 or i >= len(a.items):
        raise PineRuntimeError(
            f"array index {i} out of bounds (size {len(a.items)})", node.line)
    return a.items[i]


def _array_set(interp, pos, named, node):
    a = _arr(pos[0], node)
    i = _i(pos[1])
    if i < 0 or i >= len(a.items):
        raise PineRuntimeError(
            f"array index {i} out of bounds (size {len(a.items)})", node.line)
    a.items[i] = pos[2]
    return NA


def _array_push(interp, pos, named, node):
    _arr(pos[0], node).items.append(pos[1])
    return NA


def _array_pop(interp, pos, named, node):
    a = _arr(pos[0], node)
    if not a.items:
        raise PineRuntimeError("array.pop() on an empty array", node.line)
    return a.items.pop()


def _array_shift(interp, pos, named, node):
    a = _arr(pos[0], node)
    if not a.items:
        raise PineRuntimeError("array.shift() on an empty array", node.line)
    return a.items.pop(0)


def _array_unshift(interp, pos, named, node):
    _arr(pos[0], node).items.insert(0, pos[1])
    return NA


def _array_size(interp, pos, named, node):
    return len(_arr(pos[0], node).items)


def _array_clear(interp, pos, named, node):
    _arr(pos[0], node).items.clear()
    return NA


def _array_fill(interp, pos, named, node):
    a = _arr(pos[0], node)
    value = pos[1]
    start = _i(pos[2], 0) if len(pos) > 2 else 0
    end = _i(pos[3], len(a.items)) if len(pos) > 3 else len(a.items)
    for i in range(max(0, start), min(len(a.items), end)):
        a.items[i] = value
    return NA


def _array_sum(interp, pos, named, node):
    vals = [num(v) for v in _arr(pos[0], node).items]
    return sum(v for v in vals if not is_na(v))


def _array_sort(interp, pos, named, node):
    a = _arr(pos[0], node)
    descending = False
    order = pos[1] if len(pos) > 1 else named.get("order")
    if order is not None and getattr(order, "path", "").endswith("descending"):
        descending = True
    a.items.sort(key=lambda v: (is_na(v), num(v) if not is_na(v) else 0),
                 reverse=descending)
    return NA


def _array_insert(interp, pos, named, node):
    _arr(pos[0], node).items.insert(_i(pos[1]), pos[2])
    return NA


def _array_remove(interp, pos, named, node):
    a = _arr(pos[0], node)
    i = _i(pos[1])
    if i < 0 or i >= len(a.items):
        raise PineRuntimeError(f"array.remove index {i} out of bounds", node.line)
    return a.items.pop(i)


def _array_includes(interp, pos, named, node):
    return pos[1] in _arr(pos[0], node).items


def _array_max(interp, pos, named, node):
    vals = [num(v) for v in _arr(pos[0], node).items if not is_na(v)]
    return max(vals) if vals else NA


def _array_min(interp, pos, named, node):
    vals = [num(v) for v in _arr(pos[0], node).items if not is_na(v)]
    return min(vals) if vals else NA


def _array_avg(interp, pos, named, node):
    vals = [num(v) for v in _arr(pos[0], node).items if not is_na(v)]
    return sum(vals) / len(vals) if vals else NA


# ---------------------------------------------------------------------- str
def _str_length(interp, pos, named, node):
    return len(pos[0] or "")


def _str_upper(interp, pos, named, node):
    return (pos[0] or "").upper()


def _str_lower(interp, pos, named, node):
    return (pos[0] or "").lower()


def _str_repeat(interp, pos, named, node):
    return (pos[0] or "") * max(0, _i(pos[1], 0))


def _str_contains(interp, pos, named, node):
    return (pos[1] or "") in (pos[0] or "")


def _str_replace_all(interp, pos, named, node):
    return (pos[0] or "").replace(pos[1] or "", pos[2] or "")


# -------------------------------------------------------------------- other
def _input(interp, path, pos, named, node):
    """Returns the override if the harness supplied one, else the default.

    This is what makes an offline parameter sweep possible: the same file runs
    under different settings without editing it."""
    default = pos[0] if pos else named.get("defval", NA)
    title = pos[1] if len(pos) > 1 else named.get("title")
    key = title if isinstance(title, str) else None
    interp.inputs_seen[key or f"#{node.uid}"] = default
    if key is not None and key in interp.overrides:
        return interp.overrides[key]
    return default


def _color(interp, path, pos, named, node):
    if path == "color.new":
        base = pos[0] if pos else "#000000"
        transparency = _i(pos[1], 0) if len(pos) > 1 else 0
        return f"{base}@{transparency}"
    if path == "color.rgb":
        return "#" + "".join(f"{_i(c, 0):02x}" for c in pos[:3])
    return f"<{path}>"


def _drawing(interp, path, pos, named, node):
    kind, _, action = path.partition(".")
    if action == "new":
        d = Drawing(kind, named)
        for i, v in enumerate(pos):
            d.props[f"arg{i}"] = v
        interp.drawings.append(d)
        return d
    if action.startswith("set_"):
        target = pos[0] if pos else None
        if isinstance(target, Drawing):
            field = action[4:]
            target.props[field] = pos[1:] if len(pos) > 2 else (
                pos[1] if len(pos) > 1 else NA)
        return NA
    if action in ("delete", "merge_cells", "cell", "cell_set_text", "clear"):
        return NA
    if action.startswith("get_"):
        target = pos[0] if pos else None
        return target.props.get(action[4:], NA) if isinstance(target, Drawing) else NA
    return NA


def _output(interp, path, pos, named, node):
    """plot/indicator/alertcondition and friends: recorded, not drawn."""
    if path in ("indicator", "strategy", "library"):
        interp.declaration = dict(named)
        return NA
    if path == "alertcondition":
        interp.alerts.append({"condition": truthy(pos[0] if pos else False),
                              "title": pos[1] if len(pos) > 1 else named.get("title")})
        return NA
    title = named.get("title") or (pos[1] if len(pos) > 1 else path)
    value = pos[0] if pos else NA
    interp.plots.setdefault(title, []).append(value)
    return NA


def _tf_in_seconds(interp, pos, named, node):
    from .platform import timeframe_seconds
    tf = pos[0] if pos else interp.platform.timeframe
    return timeframe_seconds(tf)


def _synthetic_intrabars(interp, count):
    """`count` sub-bars for the CURRENT chart bar, as one plausible path.

    Two properties are guaranteed and they are what make this defensible rather
    than decorative: the sub-bars span exactly the chart bar's own high and low,
    and their volumes sum exactly to its volume. Nothing is created and nothing
    is lost - only distributed.

    The path is deterministic. An up bar goes open, down to the low, up to the
    high, back to the close; a down bar mirrors it. That is a convention, not a
    measurement, and it is the same convention every time so a result can be
    compared with the previous run."""
    i = interp.bar_index
    o = interp.hist["open"][i]
    h = interp.hist["high"][i]
    lo = interp.hist["low"][i]
    c = interp.hist["close"][i]
    v = interp.hist["volume"][i]
    if any(x is None or is_na(x) for x in (o, h, lo, c)):
        return [], [], [], []
    total = 0.0 if v is None or is_na(v) else float(v)

    up = c >= o
    legs = [o, lo, h, c] if up else [o, h, lo, c]
    highs, lows, closes, vols = [], [], [], []
    # Walk the path in `count` equal steps, so the sub-bars tile the whole leg
    # rather than sampling points on it.
    steps = max(1, count)
    prev = legs[0]
    for k in range(steps):
        t0 = k * 3.0 / steps
        t1 = (k + 1) * 3.0 / steps
        a = _path_point(legs, t0)
        b = _path_point(legs, t1)
        seg_hi = max(a, b, prev)
        seg_lo = min(a, b, prev)
        highs.append(seg_hi)
        lows.append(seg_lo)
        closes.append(b)
        vols.append(total / steps)
        prev = b
    # The extremes must be the bar's own, not merely close to them: a profile
    # built from sub-bars that never reach the high would put volume where the
    # chart says none traded.
    if highs:
        highs[highs.index(max(highs))] = h
        lows[lows.index(min(lows))] = lo
        closes[-1] = c
    return highs, lows, closes, vols


def _path_point(legs, t):
    """Position along a three-leg path at parameter t in [0, 3]."""
    t = max(0.0, min(3.0, t))
    seg = min(2, int(t))
    frac = t - seg
    return legs[seg] + (legs[seg + 1] - legs[seg]) * frac


def _request_lower_tf(interp, pos, named, node):
    """No intrabar data exists offline, so this returns na — deliberately.

    Fabricating sub-bars would produce a profile that LOOKS measured and is
    invented. Returning na exercises the script's own fallback, which is the
    behaviour worth testing anyway."""
    count = getattr(interp.platform, "intrabars", 0) or 0
    if count > 0:
        interp.approximations.add(
            f"request.security_lower_tf() returned {count} SYNTHETIC sub-bars "
            "per chart bar; they span the bar's own high and low and their "
            "volumes sum to its volume, but the path between them is invented. "
            "Anything measured from them describes the synthesis, not a market")
        hi, lo, cl, vol = _synthetic_intrabars(interp, count)
        expr = pos[2] if len(pos) > 2 else None
        if isinstance(expr, (list, tuple)):
            # Match the requested series to the arguments, by name, from the
            # syntax tree - the caller may ask for any subset in any order.
            args = getattr(node, "b", None) or []
            expr_node = args[2][1] if len(args) > 2 else None
            names = []
            if getattr(expr_node, "kind", None) == "tuple":
                for item in (expr_node.a or []):
                    names.append(getattr(item, "a", None)
                                 if getattr(item, "kind", None) == "name" else None)
            by_name = {"high": hi, "low": lo, "close": cl, "volume": vol}
            out = []
            for k in range(len(expr)):
                series = by_name.get(names[k] if k < len(names) else None)
                out.append(PineArray(list(series if series is not None else cl)))
            return out
        return PineArray(list(cl))

    interp.approximations.add(
        "request.security_lower_tf() returned na (no intrabar data offline); "
        "the script's fallback path ran instead")
    # The shape must match what was ASKED for. Requesting a tuple of four
    # series and handing back a single na turns a destructuring assignment
    # into a crash, which says nothing about the script under test.
    # An EMPTY ARRAY, not na. Pine returns an array of intrabar values, and a
    # script is entitled to call array.size() on it without a na check —
    # volume_pro does exactly that. Empty satisfies both idioms: na() is false,
    # size() is 0, and every consumer takes its no-data path.
    expr = pos[2] if len(pos) > 2 else None
    if isinstance(expr, (list, tuple)):
        return [PineArray([]) for _ in expr]
    return PineArray([])


# The price series a higher-timeframe bar can answer directly. Anything else
# has to be recomputed in its own context, which is a different job.
HTF_SERIES = {
    "open": lambda b: b["open"],
    "high": lambda b: b["high"],
    "low": lambda b: b["low"],
    "close": lambda b: b["close"],
    "volume": lambda b: b["volume"],
    "time": lambda b: b["time"],
    "hl2": lambda b: (b["high"] + b["low"]) / 2.0,
    "hlc3": lambda b: (b["high"] + b["low"] + b["close"]) / 3.0,
    "ohlc4": lambda b: (b["open"] + b["high"] + b["low"] + b["close"]) / 4.0,
    "hlcc4": lambda b: (b["high"] + b["low"] + b["close"] * 2) / 4.0,
}


# Fixed the moment a bar opens, so asking for them on a FORMING bar is not
# repainting - they cannot change. Everything else on an unfinished bar can.
SETTLED_AT_OPEN = {"open", "time"}


def _htf_buckets(interp, seconds):
    """The chart bars grouped into higher-timeframe candles.

    Cached per timeframe: a script calling request.security on every bar would
    otherwise rebuild the whole series every time."""
    cache = getattr(interp, "_htf_cache", None)
    if cache is None:
        cache = {}
        interp._htf_cache = cache
    if seconds in cache:
        return cache[seconds]

    period = seconds * 1000
    bars, index = [], []
    current = None
    for bar in interp.bars:
        stamp = bar.get("time")
        if stamp is None:
            index.append(None)
            continue
        slot = int(stamp // period)
        if current is None or slot != current["slot"]:
            current = {"slot": slot, "open": bar["open"], "high": bar["high"],
                       "low": bar["low"], "close": bar["close"],
                       "volume": bar.get("volume") or 0.0, "time": bar["time"]}
            bars.append(current)
        else:
            current["high"] = max(current["high"], bar["high"])
            current["low"] = min(current["low"], bar["low"])
            current["close"] = bar["close"]
            current["volume"] = (current["volume"] or 0.0) + (bar.get("volume") or 0.0)
        index.append(len(bars) - 1)
    cache[seconds] = (bars, index)
    return cache[seconds]


def _series_ref(node):
    """(name, offset) for a plain price series, or None.

    Read from the syntax tree rather than from the value, because by the time a
    builtin runs its arguments are already numbers and `close` is
    indistinguishable from any other float.

    The offset counts HIGHER-timeframe bars, not chart bars: `high[1]` on a
    daily request is yesterday's high, which is the most common thing anyone
    asks a higher timeframe for."""
    kind = getattr(node, "kind", None)
    if kind == "name" and node.a in HTF_SERIES:
        return node.a, 0
    if kind == "history":
        base, back = node.a, node.b
        if (getattr(base, "kind", None) == "name" and base.a in HTF_SERIES
                and getattr(back, "kind", None) == "num"):
            try:
                return base.a, int(back.a)
            except (TypeError, ValueError):
                return None
    return None


def _expression_refs(node):
    """The series an expression asks for, or None if it asks for something else.

    A tuple is one call answering several questions, which is how anyone writes
    this once they notice TradingView caps a script at 40 security calls."""
    if node is None:
        return None
    if getattr(node, "kind", None) == "tuple":
        parts = []
        for item in (node.a or []):
            ref = _series_ref(item)
            if ref is None:
                return None
            parts.append(ref)
        return parts or None
    ref = _series_ref(node)
    return [ref] if ref else None


def _lookahead_on(pos, named):
    for value in list(pos[3:]) + list((named or {}).values()):
        path = getattr(value, "path", "")
        if isinstance(path, str) and path.endswith("lookahead_on"):
            return True
    return False


def _request_security(interp, pos, named, node):
    """A higher-timeframe value, aggregated from the chart bars.

    Only the bar that has CLOSED is served, which is what lookahead_off means
    and the reason it does not repaint: a chart bar in the middle of an hourly
    candle sees the PREVIOUS hourly bar. Serving the forming one would produce
    results that cannot happen live."""
    if len(pos) < 3:
        return pos[-1] if pos else NA

    args = getattr(node, "b", None) or []
    expr_node = args[2][1] if len(args) > 2 else None
    refs = _expression_refs(expr_node)
    is_tuple = getattr(expr_node, "kind", None) == "tuple"
    tf = pos[1]
    seconds = timeframe_seconds(tf) if isinstance(tf, str) else NA

    if refs is None or is_na(seconds) or not interp.bars:
        interp.approximations.add(
            "request.security() fell back to the chart-timeframe value for a "
            "computed expression; only plain price series are aggregated offline")
        return pos[2]

    chart_seconds = timeframe_seconds(interp.platform.timeframe)
    if not is_na(chart_seconds) and seconds <= chart_seconds:
        # Same or lower timeframe: the chart bar IS the answer.
        return pos[2]

    bars, index = _htf_buckets(interp, int(seconds))
    slot = index[interp.bar_index] if interp.bar_index < len(index) else None
    if slot is None:
        return pos[2]
    # lookahead_off serves the last CLOSED bar; lookahead_on serves the forming
    # one, which is exactly the repainting people reach for it by mistake.
    ahead = _lookahead_on(pos, named)
    base = slot if ahead else slot - 1

    values = []
    for name, back in refs:
        use = base - back
        # lookahead_on ALONE serves the bar still forming, which repaints. With
        # an offset it does not: `high[1]` with lookahead_on is the previous
        # completed bar, and asking for it that way is the standard idiom for a
        # previous-day high precisely BECAUSE it cannot repaint. Warning about
        # the safe form would train the reader to ignore the warning.
        if ahead and back == 0 and name not in SETTLED_AT_OPEN:
            interp.approximations.add(
                "request.security() asked for the FORMING higher-timeframe bar "
                "(lookahead_on with no history offset); that value repaints on "
                "a live chart")
        values.append(NA if use < 0 else HTF_SERIES[name](bars[use]))
    return values if is_tuple else values[0]


def _shape_note(interp, pos, named, node):
    return NA


def _timeframe_change(interp, pos, named, node):
    """True on the FIRST bar of a new higher-timeframe period.

    The buckets that request.security() aggregates over already say which
    higher-timeframe candle each chart bar belongs to, so a boundary is simply
    the bar whose bucket differs from the one before it.

    This used to return false unconditionally, which meant a script gated on it
    took its "nothing new" path for the entire run - the branch never executed
    at all, and every test of it agreed that nothing happened."""
    tf = pos[0] if pos else None
    if not isinstance(tf, str) or not interp.bars:
        return False
    seconds = timeframe_seconds(tf)
    if is_na(seconds):
        return False
    _bars, index = _htf_buckets(interp, int(seconds))
    i = interp.bar_index
    if i >= len(index) or index[i] is None:
        return False
    # The first bar of the series opens a period by definition.
    if i == 0:
        return True
    return index[i] != index[i - 1]


SESSION_CACHE = {}


def _zone(name):
    """A tzinfo for a Pine timezone string, or None when it cannot be resolved.

    IANA names go through zoneinfo so their DST rules apply. Fixed offsets like
    "UTC-5" are accepted too, and are exactly as wrong here as they are on a
    chart - which is the point of supporting both."""
    if not name:
        return datetime.timezone.utc
    key = str(name)
    if key in SESSION_CACHE:
        return SESSION_CACHE[key]
    zone = None
    m = re.fullmatch(r"(?:UTC|GMT)([+-]\d{1,2})(?::?(\d{2}))?", key.strip())
    if m:
        hours = int(m.group(1))
        mins = int(m.group(2) or 0) * (1 if hours >= 0 else -1)
        zone = datetime.timezone(datetime.timedelta(hours=hours, minutes=mins))
    else:
        try:
            zone = zoneinfo.ZoneInfo(key)
        except Exception:
            zone = None
    SESSION_CACHE[key] = zone
    return zone


def _parse_session(spec):
    """(start_minute, end_minute, {pine weekdays}) from "HHMM-HHMM:1234567"."""
    text = str(spec).strip()
    days = None
    if ":" in text:
        text, mask = text.split(":", 1)
        days = {int(c) for c in mask.strip() if c.isdigit()}
    m = re.fullmatch(r"(\d{4})\s*-\s*(\d{4})", text.strip())
    if not m:
        return None
    def minutes(hhmm):
        return int(hhmm[:2]) * 60 + int(hhmm[2:])
    return minutes(m.group(1)), minutes(m.group(2)), days


def _time_call(interp, pos, named, node):
    """`time(timeframe, session, timezone)` - the bar's time when it falls
    inside the session, na when it does not.

    Pine numbers weekdays from 1 = Sunday, which is not Python's numbering and
    is the kind of off-by-one that silently shifts a whole day mask."""
    if len(pos) < 2:
        return interp.hist["time"][-1] if interp.hist["time"] else NA
    if not interp.hist["time"]:
        return NA
    stamp = interp.hist["time"][-1]
    if is_na(stamp):
        return NA

    parsed = _parse_session(pos[1])
    if parsed is None:
        interp.approximations.add(
            f"session spec {pos[1]!r} could not be parsed; time() returned na")
        return NA
    start, end, days = parsed

    tzname = pos[2] if len(pos) > 2 else (named.get("timezone") if named else None)
    zone = _zone(tzname)
    if zone is None:
        interp.approximations.add(
            f"timezone {tzname!r} is not a zone this machine knows; the session "
            "was measured in UTC instead")
        zone = datetime.timezone.utc

    local = datetime.datetime.fromtimestamp(stamp / 1000.0, tz=zone)
    minute = local.hour * 60 + local.minute
    # Pine: 1 = Sunday. Python: Monday = 0.
    pine_day = (local.weekday() + 1) % 7 + 1
    if days and pine_day not in days:
        return NA

    inside = start <= minute < end if start < end else (minute >= start or minute < end)
    return stamp if inside else NA


def _cast_int(interp, pos, named, node):
    """`int(x)` truncates TOWARD ZERO, which is not what round() does and not
    what floor() does for negatives. Pine truncates; so does this."""
    v = num(pos[0] if pos else NA)
    return NA if is_na(v) else int(v)


def _cast_float(interp, pos, named, node):
    v = num(pos[0] if pos else NA)
    return NA if is_na(v) else float(v)


def _cast_bool(interp, pos, named, node):
    return truthy(pos[0]) if pos else False


def _cast_string(interp, pos, named, node):
    return _tostring(interp, pos, named, node)


def _array_sort_indices(interp, pos, named, node):
    a = _arr(pos[0], node)
    order = pos[1] if len(pos) > 1 else named.get("order")
    descending = getattr(order, "path", "").endswith("descending")
    idx = sorted(range(len(a.items)),
                 key=lambda i: (is_na(a.items[i]),
                                num(a.items[i]) if not is_na(a.items[i]) else 0),
                 reverse=descending)
    return PineArray(idx)


def _str_startswith(interp, pos, named, node):
    return (pos[0] or "").startswith(pos[1] or "")


def _str_endswith(interp, pos, named, node):
    return (pos[0] or "").endswith(pos[1] or "")


def _str_substring(interp, pos, named, node):
    text = pos[0] or ""
    start = _i(pos[1], 0) if len(pos) > 1 else 0
    end = _i(pos[2], len(text)) if len(pos) > 2 else len(text)
    return text[start:end]


def _str_split(interp, pos, named, node):
    return PineArray((pos[0] or "").split(pos[1] or ","))


def _str_pos(interp, pos, named, node):
    found = (pos[0] or "").find(pos[1] or "")
    return NA if found < 0 else found


def _timestamp(interp, pos, named, node):
    """Milliseconds since the epoch, UTC.

    Pine's timestamp() takes a timezone as an optional first argument; the
    offline run treats every session as UTC and says so, because a date window
    that shifts by a timezone is a different date window."""
    import calendar
    import datetime
    values = [v for v in pos if not isinstance(v, str)]
    strings = [v for v in pos if isinstance(v, str)]
    # Pine takes the timezone as an optional FIRST argument. A date built in
    # Tokyo and one built in New York are different instants, and treating them
    # as the same one made every date window silently wrong by up to a day.
    zone = _zone(strings[0]) if strings else datetime.timezone.utc
    if strings and zone is None:
        interp.approximations.add(
            f"timestamp() was given timezone {strings[0]!r}, which this machine "
            "does not know; UTC was used instead")
        zone = datetime.timezone.utc
    if len(values) < 3:
        return NA
    y, mo, d = (_i(values[0]), _i(values[1]), _i(values[2]))
    h = _i(values[3], 0) if len(values) > 3 else 0
    mi = _i(values[4], 0) if len(values) > 4 else 0
    s = _i(values[5], 0) if len(values) > 5 else 0
    try:
        dt = datetime.datetime(y, mo, d, h, mi, s, tzinfo=zone)
    except ValueError:
        return NA
    # timestamp() from the zone it was given, not from UTC pretending to be it.
    return int(dt.timestamp() * 1000)


def _year(interp, pos, named, node):
    return _date_part(interp, pos, "year")


def _month(interp, pos, named, node):
    return _date_part(interp, pos, "month")


def _dayofmonth(interp, pos, named, node):
    return _date_part(interp, pos, "day")


def _hour(interp, pos, named, node):
    return _date_part(interp, pos, "hour")


def _minute(interp, pos, named, node):
    return _date_part(interp, pos, "minute")


def _dayofweek(interp, pos, named, node):
    return _date_part(interp, pos, "dayofweek")


def _date_part(interp, pos, part):
    import datetime
    ms = num(pos[0]) if pos else (interp.hist["time"][-1] if interp.hist["time"] else NA)
    if is_na(ms):
        return NA
    dt = datetime.datetime.fromtimestamp(float(ms) / 1000.0, datetime.timezone.utc)
    return {"year": dt.year, "month": dt.month, "day": dt.day, "hour": dt.hour,
            "minute": dt.minute, "dayofweek": (dt.weekday() + 1) % 7 + 1}[part]


def _alert(interp, pos, named, node):
    interp.alerts.append({"message": pos[0] if pos else "", "fired": True})
    return NA


def _runtime_error(interp, pos, named, node):
    raise PineRuntimeError(f"runtime.error(): {pos[0] if pos else ''}", node.line)


def _barstate(interp, path, pos, named, node):
    return NA


TABLE = {
    "na": _na, "nz": _nz, "alert": _alert, "time": _time_call,
    "int": _cast_int, "float": _cast_float, "bool": _cast_bool,
    "string": _cast_string,
    "timeframe.in_seconds": _tf_in_seconds,
    "timeframe.change": _timeframe_change,
    "request.security": _request_security,
    "request.security_lower_tf": _request_lower_tf,
    "str.tostring": _tostring, "str.tonumber": _tonumber,
    "str.length": _str_length, "str.upper": _str_upper, "str.lower": _str_lower,
    "str.repeat": _str_repeat, "str.contains": _str_contains,
    "str.replace_all": _str_replace_all,
    "str.startswith": _str_startswith, "str.endswith": _str_endswith,
    "str.substring": _str_substring, "str.split": _str_split, "str.pos": _str_pos,
    "array.sort_indices": _array_sort_indices,
    "timestamp": _timestamp, "year": _year, "month": _month,
    "dayofmonth": _dayofmonth, "hour": _hour, "minute": _minute,
    "dayofweek": _dayofweek,
    "runtime.error": _runtime_error,

    "math.abs": _math1(abs), "math.floor": _math1(lambda v: int(math.floor(v))),
    "math.ceil": _math1(lambda v: int(math.ceil(v))), "math.sqrt": _math1(math.sqrt),
    "math.log": _math1(math.log), "math.log10": _math1(math.log10),
    "math.exp": _math1(math.exp), "math.sign": _math1(lambda v: (v > 0) - (v < 0)),
    "math.round": _math_round,
    "math.max": _math_minmax(max), "math.min": _math_minmax(min),
    "math.pow": lambda i, p, n, nd: NA if any(is_na(num(x)) for x in p[:2])
    else float(num(p[0])) ** float(num(p[1])),
    "math.avg": lambda i, p, n, nd: (sum(num(x) for x in p) / len(p)) if p and not any(
        is_na(num(x)) for x in p) else NA,

    "ta.sma": _ta_sma, "ta.ema": _ta_ema, "ta.rma": _ta_rma,
    "ta.highest": _ta_highest, "ta.lowest": _ta_lowest,
    "ta.tr": _ta_tr, "ta.atr": _ta_atr, "ta.change": _ta_change, "ta.cum": _ta_cum,
    "ta.pivothigh": _ta_pivothigh, "ta.pivotlow": _ta_pivotlow,
    "ta.crossover": _ta_crossover, "ta.crossunder": _ta_crossunder,
    "ta.barssince": _ta_barssince, "ta.valuewhen": _ta_valuewhen,
    "ta.cross": _ta_cross, "ta.stdev": _ta_stdev, "ta.wma": _ta_wma,
    "ta.rsi": _ta_rsi,

    "array.new": _array_new, "array.get": _array_get, "array.set": _array_set,
    "array.push": _array_push, "array.pop": _array_pop, "array.shift": _array_shift,
    "array.unshift": _array_unshift, "array.size": _array_size,
    "array.clear": _array_clear, "array.fill": _array_fill, "array.sum": _array_sum,
    "array.sort": _array_sort, "array.insert": _array_insert,
    "array.remove": _array_remove, "array.includes": _array_includes,
    "array.max": _array_max, "array.min": _array_min, "array.avg": _array_avg,
}

# `array.new<float>(...)` parses as a call to `array.new`, so the generic forms
# resolve to the same implementation.
for _t in ("float", "int", "bool", "string", "color", "box", "line", "label"):
    TABLE[f"array.new_{_t}"] = _array_new
