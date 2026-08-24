"""
Runtime values, series history, and the builtin library.

THE EXECUTION MODEL, stated once because everything below depends on it:
Pine runs the whole script once per bar, left to right, and every variable
keeps a history indexed backwards from the current bar. `close[1]` is the
previous bar's close; `myVar[2]` is what myVar held two bars ago.

This interpreter runs CONFIRMED BARS ONLY — one pass per bar, no intrabar
ticks. That is a real limitation and it is worth naming: a bug that only
appears on a realtime tick (a `var` array mutated on a tick that turns out not
to count) cannot be reproduced here. Those get lint rules instead.

Stateful builtins (`ta.sma` and friends) keep their state per CALL SITE, keyed
by the AST node's uid. Two `ta.sma` calls in different places are two
independent averages, exactly as in Pine.
"""
import math


NA = None                       # Pine's na is modelled as Python None


def is_na(v):
    return v is None or (isinstance(v, float) and math.isnan(v))


def nz(v, replacement=0):
    return replacement if is_na(v) else v


def truthy(v):
    """Pine treats na as false in a condition, and that is load-bearing: the
    whole `na(x) or x != y` guard idiom depends on it short-circuiting."""
    if is_na(v):
        return False
    return bool(v)


def num(v):
    """Coerces to a number for arithmetic, preserving na."""
    if is_na(v):
        return None
    if isinstance(v, bool):
        return 1 if v else 0
    return v


class PineRuntimeError(Exception):
    def __init__(self, message, line=None):
        super().__init__(f"line {line}: {message}" if line else message)
        self.line = line


class Series:
    """One variable's history, newest last.

    Storing every bar is deliberate. Capping it would silently change what
    `x[500]` returns, and a value that quietly becomes na is exactly the class
    of bug this interpreter exists to catch."""
    __slots__ = ("values", "current", "has_current", "inited")

    def __init__(self):
        self.values = []
        self.current = NA
        self.has_current = False
        self.inited = False

    def set(self, value):
        self.current = value
        self.has_current = True

    def get(self, offset=0):
        if offset == 0:
            return self.current
        idx = len(self.values) - offset
        if idx < 0 or idx >= len(self.values):
            return NA
        return self.values[idx]

    def commit(self):
        """A series not assigned on this bar KEEPS its previous value.

        Appending na instead would be the obvious implementation and it is
        wrong: a `var` inside an if-block that did not run this bar would lose
        everything it holds, which is the opposite of what var means."""
        if self.has_current:
            self.values.append(self.current)
        else:
            carried = self.values[-1] if self.values else NA
            self.values.append(carried)
            self.current = carried
        self.has_current = False


class PineArray:
    """Pine arrays are reference objects. Mutating one through any binding
    mutates it everywhere, which is precisely why a `var` array is not rolled
    back on a realtime tick — the variable is restored, the object is not."""
    __slots__ = ("items",)

    def __init__(self, items=None):
        self.items = list(items or [])

    def __repr__(self):
        return f"PineArray({self.items!r})"


class UDTInstance:
    __slots__ = ("type_name", "fields")

    def __init__(self, type_name, fields):
        self.type_name, self.fields = type_name, fields

    def __repr__(self):
        return f"{self.type_name}({self.fields!r})"


class Drawing:
    """A box/line/label/table. Never rendered — recorded, so a test can assert
    on how many were created and where they were put. That count is the whole
    point: the drawing-budget bug this repo shipped was invisible in the source
    and obvious in a count."""
    __slots__ = ("kind", "props", "uid")
    _n = [0]

    def __init__(self, kind, props):
        self.kind, self.props = kind, dict(props)
        Drawing._n[0] += 1
        self.uid = Drawing._n[0]

    def __repr__(self):
        return f"<{self.kind}#{self.uid}>"


# ---------------------------------------------------------------------------
# Stateful ta.* helpers. Each instance belongs to one call site.
# ---------------------------------------------------------------------------
class RollingWindow:
    __slots__ = ("buf", "length")

    def __init__(self, length):
        self.buf, self.length = [], length

    def push(self, value):
        self.buf.append(value)
        if len(self.buf) > self.length:
            self.buf.pop(0)
        return self.buf

    def full(self):
        return len(self.buf) >= self.length


def ta_sma(state, value, length):
    length = int(nz(length, 0))
    if length <= 0 or is_na(value):
        return NA
    w = state.setdefault("w", RollingWindow(length))
    w.length = length
    buf = w.push(float(value))
    if len(buf) < length:
        return NA
    return sum(buf[-length:]) / length


def ta_ema(state, value, length):
    length = int(nz(length, 0))
    if length <= 0 or is_na(value):
        return NA
    alpha = 2.0 / (length + 1)
    prev = state.get("prev")
    seed = state.setdefault("seed", [])
    if prev is None:
        seed.append(float(value))
        if len(seed) < length:
            return NA
        prev = sum(seed) / len(seed)
        state["prev"] = prev
        return prev
    cur = alpha * float(value) + (1 - alpha) * prev
    state["prev"] = cur
    return cur


def ta_rma(state, value, length):
    length = int(nz(length, 0))
    if length <= 0 or is_na(value):
        return NA
    prev = state.get("prev")
    seed = state.setdefault("seed", [])
    if prev is None:
        seed.append(float(value))
        if len(seed) < length:
            return NA
        prev = sum(seed) / len(seed)
        state["prev"] = prev
        return prev
    cur = (prev * (length - 1) + float(value)) / length
    state["prev"] = cur
    return cur


def ta_extreme(state, value, length, pick):
    length = int(nz(length, 0))
    if length <= 0 or is_na(value):
        return NA
    w = state.setdefault("w", RollingWindow(length))
    w.length = length
    buf = w.push(float(value))
    if len(buf) < length:
        return NA
    return pick(buf[-length:])


def ta_pivot(highs, lows, left, right, want_high):
    """A pivot is confirmed `right` bars after it happened.

    The window INCLUDES the current bar, which is what makes a pivot able to
    appear and then vanish on a realtime chart. Here every bar is confirmed, so
    the value is stable — the difference is documented rather than simulated."""
    left, right = int(nz(left, 0)), int(nz(right, 0))
    src = highs if want_high else lows
    if len(src) < left + right + 1:
        return NA
    window = src[-(left + right + 1):]
    centre = window[right] if False else window[left]
    for i, v in enumerate(window):
        if i == left:
            continue
        if want_high and v >= centre:
            return NA
        if not want_high and v <= centre:
            return NA
    return centre


def format_number(value, fmt):
    """str.tostring's format strings: '#.##', '#.#', '#'."""
    if is_na(value):
        return "NaN"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(fmt, str) and fmt.startswith("#"):
        decimals = len(fmt.split(".")[1]) if "." in fmt else 0
        return f"{float(value):.{decimals}f}"
    if isinstance(value, int):
        return str(value)
    text = f"{float(value):.10f}".rstrip("0").rstrip(".")
    return text or "0"
