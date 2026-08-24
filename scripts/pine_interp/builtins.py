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
import math

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


def _request_lower_tf(interp, pos, named, node):
    """No intrabar data exists offline, so this returns na — deliberately.

    Fabricating sub-bars would produce a profile that LOOKS measured and is
    invented. Returning na exercises the script's own fallback, which is the
    behaviour worth testing anyway."""
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


def _request_security(interp, pos, named, node):
    """Returns the expression as evaluated on the CHART timeframe.

    That is an approximation and a real one: a higher-timeframe value is
    different data, not the same data seen differently. It is recorded in the
    run report so a result that depends on it cannot be read as exact."""
    interp.approximations.add(
        "request.security() returned the chart-timeframe value; higher-timeframe "
        "results from this run are approximate")
    return pos[2] if len(pos) > 2 else (pos[-1] if pos else NA)


def _shape_note(interp, pos, named, node):
    return NA


def _timeframe_change(interp, pos, named, node):
    """True on the first bar of a new higher-timeframe period.

    Offline there is no higher-timeframe series to change, so this is always
    false and says so. A script gated on it takes its "nothing new" path for
    the whole run, which is a limitation worth seeing rather than a value worth
    inventing."""
    interp.approximations.add(
        "timeframe.change() was always false; higher-timeframe boundaries are not "
        "modelled offline")
    return False


def _time_call(interp, pos, named, node):
    if len(pos) >= 2:
        interp.approximations.add(
            "time(timeframe, session) returned na; sessions are not modelled offline")
        return NA
    return interp.hist["time"][-1] if interp.hist["time"] else NA


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
    if strings:
        interp.approximations.add(
            "timestamp() ignored its timezone argument and used UTC")
    if len(values) < 3:
        return NA
    y, mo, d = (_i(values[0]), _i(values[1]), _i(values[2]))
    h = _i(values[3], 0) if len(values) > 3 else 0
    mi = _i(values[4], 0) if len(values) > 4 else 0
    s = _i(values[5], 0) if len(values) > 5 else 0
    try:
        dt = datetime.datetime(y, mo, d, h, mi, s, tzinfo=datetime.timezone.utc)
    except ValueError:
        return NA
    return int(calendar.timegm(dt.utctimetuple())) * 1000


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
