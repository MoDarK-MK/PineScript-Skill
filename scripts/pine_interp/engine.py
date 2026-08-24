"""
The evaluator: walks the AST once per bar and keeps series history.

Design notes worth knowing before reading:

  * A BLOCK evaluates to the value of its last statement. Pine's `if` and
    `switch` are expressions, and this one rule is what makes that work without
    a separate expression grammar for them.

  * `var` is initialised on the bar it first executes and then never
    re-initialised. Plain declarations re-run every bar. That distinction is
    the single most common source of Pine bugs, so it is modelled exactly.

  * History lives per DECLARATION SITE, not per name. Two `float x` in
    different function bodies are different series, which is why the scope
    chain hands out Series objects rather than raw values.

  * Drawing calls are recorded, not rendered. What a test wants to know is how
    MANY were made and where — the drawing-budget bug this repo shipped was
    invisible in the source and obvious in a count.
"""
import math

from .runtime import (NA, Drawing, PineArray, PineRuntimeError, Series,
                      coerce_declared, is_pine_int, pine_divide,
                      UDTInstance, format_number, is_na, num, nz, ta_ema,
                      ta_extreme, ta_pivot, ta_rma, ta_sma, truthy)
from .platform import PASSTHROUGH_PREFIXES, Platform, timeframe_seconds
from .syntax import Node, parse


class BreakSignal(Exception):
    pass


class ContinueSignal(Exception):
    pass


class Scope:
    __slots__ = ("vars", "parent")

    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent

    def lookup(self, name):
        s = self
        while s is not None:
            if name in s.vars:
                return s.vars[name]
            s = s.parent
        return None

    def declare(self, name, series):
        self.vars[name] = series


class Interpreter:
    def __init__(self, source, bars, inputs=None, max_bars=None, platform=None):
        self.ast = parse(source)
        self.bars = bars
        self.overrides = dict(inputs or {})
        self.max_bars = max_bars
        self.platform = platform or Platform()
        self.is_last = False
        self.approximations = set()

        self.globals = Scope()
        self.series = {}            # uid -> Series (declaration-site history)
        self.state = {}             # uid -> dict (stateful builtins)
        self.expr_hist = {}         # uid -> history of an expression under []
        self.functions = {}
        self.types = {}
        self.drawings = []
        self.plots = {}
        self.alerts = []
        self.logs = []
        self.inputs_seen = {}

        self.bar_index = 0
        self.open = self.high = self.low = self.close = self.volume = NA
        self.hl2 = self.hlc3 = self.ohlc4 = self.hlcc4 = NA
        # hl2/hlc3/ohlc4/hlcc4 are built-in SERIES, not expressions computed on
        # the spot: `hlc3[3]` has to work, so they carry history like any other.
        self.hist = {"open": [], "high": [], "low": [], "close": [],
                     "volume": [], "time": [],
                     "hl2": [], "hlc3": [], "ohlc4": [], "hlcc4": []}
        self.declared_this_bar = set()

    # ------------------------------------------------------------------ run
    def run(self):
        """Executes the script once per bar. Returns self for chaining."""
        total = len(self.bars) if self.max_bars is None else min(len(self.bars),
                                                                self.max_bars)
        for i in range(total):
            bar = self.bars[i]
            self.bar_index = i
            self.open = bar.get("open")
            self.high = bar.get("high")
            self.low = bar.get("low")
            self.close = bar.get("close")
            self.volume = bar.get("volume", 0)
            for key in ("open", "high", "low", "close", "volume", "time"):
                self.hist[key].append(bar.get(key))
            o, h, l, c = (bar.get("open"), bar.get("high"),
                          bar.get("low"), bar.get("close"))
            self.hl2 = None if None in (h, l) else (h + l) / 2
            self.hlc3 = None if None in (h, l, c) else (h + l + c) / 3
            self.ohlc4 = None if None in (o, h, l, c) else (o + h + l + c) / 4
            self.hlcc4 = None if None in (h, l, c) else (h + l + c + c) / 4
            for key in ("hl2", "hlc3", "ohlc4", "hlcc4"):
                self.hist[key].append(getattr(self, key))
            self.is_last = (i == total - 1)
            self.declared_this_bar = set()
            try:
                self.exec_block(self.ast, self.globals)
            except (BreakSignal, ContinueSignal):
                raise PineRuntimeError("break/continue outside a loop")
            for s in self.series.values():
                s.commit()
        return self

    # ------------------------------------------------------------ statements
    def exec_block(self, stmts, scope):
        value = NA
        for st in stmts:
            value = self.exec_stmt(st, scope)
        return value

    def exec_stmt(self, node, scope):
        kind = node.kind
        if kind == "decl":
            return self.exec_decl(node, scope)
        if kind == "assign":
            return self.exec_assign(node, scope)
        if kind == "setattr":
            return self.exec_setattr(node, scope)
        if kind == "tupledecl":
            return self.exec_tupledecl(node, scope)
        if kind == "expr":
            return self.eval(node.a, scope)
        if kind == "if":
            return self.exec_if(node, scope)
        if kind == "for":
            return self.exec_for(node, scope)
        if kind == "forin":
            return self.exec_forin(node, scope)
        if kind == "while":
            return self.exec_while(node, scope)
        if kind == "funcdef":
            self.functions[node.a] = (node.b, node.c)
            return NA
        if kind == "typedef":
            self.types[node.a] = node.b
            return NA
        if kind == "break":
            raise BreakSignal()
        if kind == "continue":
            raise ContinueSignal()
        if kind == "block":
            return self.exec_block(node.a, Scope(scope))
        raise PineRuntimeError(f"cannot execute {kind}", node.line)

    def series_for(self, node):
        s = self.series.get(node.uid)
        if s is None:
            s = Series()
            self.series[node.uid] = s
        return s

    def exec_decl(self, node, scope):
        qualifier, name = node.a
        s = self.series_for(node)
        # The declared type is carried on the series, not just applied once:
        # `float x = 0.0` followed by `x := array.size(a)` must still hold a
        # float, or the next division silently truncates.
        s.decl_type = node.c
        if qualifier in ("var", "varip"):
            # Initialised once, on the bar it first runs, and never again. On
            # every later bar it is left untouched — commit() carries the value
            # forward, so there is nothing to re-assign here.
            if not s.inited:
                s.set(coerce_declared(self.eval(node.b, scope), s.decl_type))
                s.inited = True
        else:
            s.set(coerce_declared(self.eval(node.b, scope), s.decl_type))
        scope.declare(name, s)
        return s.get(0)

    def exec_assign(self, node, scope):
        name, op = node.a, node.c
        s = scope.lookup(name)
        if s is None:
            raise PineRuntimeError(
                f"'{name}' is reassigned but was never declared "
                f"(TradingView: Undeclared identifier)", node.line)
        value = self.eval(node.b, scope)
        if op != ":=":
            cur = num(s.get(0))
            rhs = num(value)
            if is_na(cur) or is_na(rhs):
                value = NA
            else:
                value = {"+=": lambda a, b: a + b, "-=": lambda a, b: a - b,
                         "*=": lambda a, b: a * b,
                         "/=": lambda a, b: pine_divide(a, b),
                         "%=": lambda a, b: a % b if b else NA}[op](cur, rhs)
        # The declared type survives reassignment. `float x = 0.0` followed by
        # `x := array.size(a)` must still hold a float, or the next division
        # truncates and the int-division fix creates the opposite bug.
        s.set(coerce_declared(value, s.decl_type))
        return value

    def exec_setattr(self, node, scope):
        target = node.a
        if target.kind != "member":
            raise PineRuntimeError("unsupported assignment target", node.line)
        obj = self.eval(target.a, scope)
        value = self.eval(node.b, scope)
        if node.c != ":=":
            cur = num(obj.fields.get(target.b))
            rhs = num(value)
            value = NA if (is_na(cur) or is_na(rhs)) else {
                "+=": lambda a, b: a + b, "-=": lambda a, b: a - b,
                "*=": lambda a, b: a * b, "/=": lambda a, b: a / b if b else NA,
                "%=": lambda a, b: a % b if b else NA}[node.c](cur, rhs)
        if not isinstance(obj, UDTInstance):
            raise PineRuntimeError(f"cannot set a field on {type(obj).__name__}",
                                   node.line)
        obj.fields[target.b] = value
        return value

    def exec_tupledecl(self, node, scope):
        values = self.eval(node.b, scope)
        if not isinstance(values, (list, tuple)):
            raise PineRuntimeError("tuple assignment from a non-tuple", node.line)
        for i, name in enumerate(node.a):
            key = (node.uid, i)
            s = self.series.get(key)
            if s is None:
                s = Series()
                self.series[key] = s
            s.set(values[i] if i < len(values) else NA)
            scope.declare(name, s)
        return NA

    def exec_if(self, node, scope):
        if truthy(self.eval(node.a, scope)):
            return self.exec_block(node.b, Scope(scope))
        if node.c is not None:
            return self.exec_block(node.c, Scope(scope))
        return NA

    def exec_for(self, node, scope):
        name, start_n, end_n, step_n = node.a
        start = int(nz(self.eval(start_n, scope), 0))
        end = int(nz(self.eval(end_n, scope), 0))
        step = int(nz(self.eval(step_n, scope), 1)) if step_n else 1
        if step == 0:
            raise PineRuntimeError("for loop step is zero", node.line)
        # Pine counts DOWN when the end is below the start. This is not a
        # nicety: `for i = 0 to size - 1` with an empty array runs with i = 0
        # and i = -1, which is a real bug this repo shipped.
        if step_n is None and end < start:
            step = -1
        inner = Scope(scope)
        s = Series()
        inner.declare(name, s)
        value = NA
        i = start
        guard = 0
        while (i <= end if step > 0 else i >= end):
            guard += 1
            if guard > 1_000_000:
                raise PineRuntimeError("for loop exceeded 1,000,000 iterations",
                                       node.line)
            s.set(i)
            try:
                value = self.exec_block(node.b, Scope(inner))
            except BreakSignal:
                break
            except ContinueSignal:
                pass
            i += step
        return value

    def exec_forin(self, node, scope):
        iterable = self.eval(node.b, scope)
        items = iterable.items if isinstance(iterable, PineArray) else list(iterable or [])
        inner = Scope(scope)
        holders = [Series() for _ in node.a]
        for nm, h in zip(node.a, holders):
            inner.declare(nm, h)
        value = NA
        for idx, item in enumerate(items):
            if len(node.a) == 2:
                holders[0].set(idx)
                holders[1].set(item)
            else:
                holders[0].set(item)
            try:
                value = self.exec_block(node.c, Scope(inner))
            except BreakSignal:
                break
            except ContinueSignal:
                continue
        return value

    def exec_while(self, node, scope):
        value, guard = NA, 0
        while truthy(self.eval(node.a, scope)):
            guard += 1
            if guard > 1_000_000:
                raise PineRuntimeError("while loop exceeded 1,000,000 iterations",
                                       node.line)
            try:
                value = self.exec_block(node.b, Scope(scope))
            except BreakSignal:
                break
            except ContinueSignal:
                continue
        return value

    # ----------------------------------------------------------- expressions
    def eval(self, node, scope):
        kind = node.kind
        if kind == "num":
            return node.a
        if kind == "str":
            return node.a
        if kind == "bool":
            return node.a
        if kind == "color":
            return node.a
        if kind == "na":
            return NA
        if kind == "name":
            return self.eval_name(node, scope)
        if kind == "binary":
            return self.eval_binary(node, scope)
        if kind == "unary":
            v = self.eval(node.b, scope)
            if node.a == "not":
                return not truthy(v)
            n = num(v)
            return NA if is_na(n) else -n
        if kind == "ternary":
            return self.eval(node.b if truthy(self.eval(node.a, scope)) else node.c,
                             scope)
        if kind == "history":
            return self.eval_history(node, scope)
        if kind == "member":
            return self.eval_member(node, scope)
        if kind == "call":
            return self.eval_call(node, scope)
        if kind == "tuple":
            return [self.eval(x, scope) for x in node.a]
        if kind == "if":
            return self.exec_if(node, scope)
        if kind == "switch":
            return self.eval_switch(node, scope)
        if kind == "block":
            return self.exec_block(node.a, Scope(scope))
        raise PineRuntimeError(f"cannot evaluate {kind}", node.line)

    BUILTIN_SERIES = {"open", "high", "low", "close", "volume", "time",
                      "hl2", "hlc3", "ohlc4", "hlcc4"}

    def eval_name(self, node, scope):
        name = node.a
        if name in self.BUILTIN_SERIES:
            return getattr(self, name) if name != "time" else self.hist["time"][-1]
        if name == "bar_index":
            return self.bar_index
        if name == "last_bar_index":
            total = len(self.bars) if self.max_bars is None else min(
                len(self.bars), self.max_bars)
            return total - 1
        if name == "na":
            return NA
        s = scope.lookup(name)
        if s is not None:
            return s.get(0)
        if name in self.types or name in self.functions:
            return Namespace(name)
        return Namespace(name)

    def eval_history(self, node, scope):
        offset = int(nz(self.eval(node.b, scope), 0))
        target = node.a
        if target.kind == "name":
            name = target.a
            if name in self.BUILTIN_SERIES:
                buf = self.hist[name]
                idx = len(buf) - 1 - offset
                return buf[idx] if 0 <= idx < len(buf) else NA
            if name == "bar_index":
                return self.bar_index - offset
            s = scope.lookup(name)
            if s is None:
                raise PineRuntimeError(f"unknown series '{name}'", node.line)
            return s.get(offset)
        # `ta.ema(close, n)[1]` — history on an EXPRESSION. This is the
        # documented non-repainting idiom for request.security(), so it is not
        # exotic at all.
        #
        # The buffer advances once per BAR, not once per evaluation: reading
        # the same history node twice in one bar must not push two entries.
        # Note the requirement this carries — the expression has to be
        # evaluated every bar for its history to be complete. One sitting
        # inside a conditional will have gaps, which is also true in Pine.
        entry = self.expr_hist.get(node.uid)
        if entry is None:
            entry = {"values": [], "bar": -1}
            self.expr_hist[node.uid] = entry
        if entry["bar"] != self.bar_index:
            entry["values"].append(self.eval(target, scope))
            entry["bar"] = self.bar_index
        idx = len(entry["values"]) - 1 - offset
        return entry["values"][idx] if 0 <= idx < len(entry["values"]) else NA

    def eval_member(self, node, scope):
        base = node.a
        if base.kind == "name" and scope.lookup(base.a) is None:
            path = f"{base.a}.{node.b}"
            constants = self.platform.constants(self)
            if path in constants:
                return constants[path]
            if path in STRATEGY_STATE:
                # No order execution is simulated, so the position is always
                # flat and every tally is zero. That is a MODEL, stated aloud —
                # not a guess. A test of a strategy's flat-path logic is valid
                # under it; a test of its backtest results is not, and the
                # approximation note says exactly that.
                self.approximations.add(
                    "strategy state is not simulated: the position is always flat "
                    "and every tally reads zero, so backtest figures from this run "
                    "mean nothing")
                return STRATEGY_STATE[path]
            if path.startswith(PASSTHROUGH_PREFIXES):
                return Namespace(path)
            return Namespace(path)
        obj = self.eval(base, scope)
        if isinstance(obj, UDTInstance):
            if node.b not in obj.fields:
                raise PineRuntimeError(
                    f"'{obj.type_name}' has no field '{node.b}'", node.line)
            return obj.fields[node.b]
        if isinstance(obj, Namespace):
            return Namespace(f"{obj.path}.{node.b}")
        raise PineRuntimeError(f"cannot read '.{node.b}' from {type(obj).__name__}",
                               node.line)

    def eval_switch(self, node, scope):
        if node.a is not None:
            subject = self.eval(node.a, scope)
            for label, value in node.b:
                if self.equals(self.eval(label, scope), subject):
                    return self.eval(value, scope)
        else:
            for label, value in node.b:
                if truthy(self.eval(label, scope)):
                    return self.eval(value, scope)
        if node.c is not None:
            return self.eval(node.c, scope)
        return NA

    @staticmethod
    def equals(a, b):
        if is_na(a) or is_na(b):
            return False
        return a == b

    def eval_binary(self, node, scope):
        op = node.a
        if op == "and":
            # Short-circuit. `na(x) or x != y` depends on it.
            return truthy(self.eval(node.b, scope)) and truthy(self.eval(node.c, scope))
        if op == "or":
            return truthy(self.eval(node.b, scope)) or truthy(self.eval(node.c, scope))
        left = self.eval(node.b, scope)
        right = self.eval(node.c, scope)
        if op == "+" and (isinstance(left, str) or isinstance(right, str)):
            return ("" if is_na(left) else str(left)) + ("" if is_na(right) else str(right))
        if op in ("==", "!="):
            same = self.equals(left, right)
            if is_na(left) and is_na(right):
                # na == na is na in Pine, which is falsy either way. This is the
                # exact trap PINE045 exists for, so the interpreter reproduces
                # it rather than being helpfully wrong.
                return False
            return same if op == "==" else not same
        if op == "+" and isinstance(left, Namespace) and isinstance(right, Namespace):
            # `display.pane + display.data_window` — Pine combines these
            # constants with +. The combination is only ever handed to a
            # `display=` parameter, so carrying both paths is enough.
            return Namespace(f"{left.path}+{right.path}")
        for side, value in (("left", left), ("right", right)):
            if isinstance(value, Namespace):
                raise PineRuntimeError(
                    f"the {side} side of '{op}' is '{value.path}', which resolved "
                    f"to a name rather than a value — it is either a builtin this "
                    f"interpreter does not know, or a typo", node.line)
        a, b = num(left), num(right)
        if is_na(a) or is_na(b):
            return NA
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            # Pine divides two integers as an INTEGER. `1 / 2` is 0 on a chart,
            # and `math.ceil(30 / 14)` is 2 rather than 3 because the truncation
            # happens before ceil is ever called. Returning the float here made
            # this interpreter agree with arithmetic instead of with Pine, and
            # vouch for a script that was miscounting on the chart.
            return pine_divide(a, b)
        if op == "%":
            return NA if b == 0 else math.fmod(a, b)
        if op == "<":
            return a < b
        if op == ">":
            return a > b
        if op == "<=":
            return a <= b
        if op == ">=":
            return a >= b
        raise PineRuntimeError(f"unknown operator {op}", node.line)

    # ----------------------------------------------------------------- calls
    def eval_call(self, node, scope):
        target = node.a
        args = [(name, self.eval(expr, scope)) for name, expr in node.b]
        positional = [v for n, v in args if n is None]
        named = {n: v for n, v in args if n is not None}

        if target.kind == "name":
            name = target.a
            if name in self.functions:
                return self.call_user(name, positional, named, node)
            if name in self.types:
                raise PineRuntimeError(f"use {name}.new(...) to construct", node.line)
            return self.call_builtin(name, positional, named, node, scope)

        if target.kind == "member":
            base = target.a
            member = target.b
            if base.kind == "name" and base.a in self.types and member == "new":
                return self.construct(base.a, positional, named, node)
            path = self.namespace_path(base, scope)
            if path is not None:
                return self.call_builtin(f"{path}.{member}", positional, named,
                                         node, scope)
            # Method-call form: `myTable.cell(...)` means `table.cell(myTable, …)`,
            # and a UDT method call means the same for its type. Pine offers both
            # spellings for the same operation, so both have to work.
            receiver = self.eval(base, scope)
            if isinstance(receiver, Drawing):
                return self.call_builtin(f"{receiver.kind}.{member}",
                                         [receiver] + positional, named, node, scope)
            if isinstance(receiver, PineArray):
                return self.call_builtin(f"array.{member}",
                                         [receiver] + positional, named, node, scope)
            if isinstance(receiver, UDTInstance) and member in self.functions:
                return self.call_user(member, [receiver] + positional, named, node)
        raise PineRuntimeError(
            "unsupported call target — the receiver is neither a namespace nor a "
            "drawing, array or user type", node.line)

    def namespace_path(self, node, scope):
        if node.kind == "name":
            return node.a if scope.lookup(node.a) is None else None
        if node.kind == "member":
            head = self.namespace_path(node.a, scope)
            return f"{head}.{node.b}" if head else None
        return None

    def construct(self, type_name, positional, named, node):
        fields = {}
        spec = self.types[type_name]
        for i, (fname, default) in enumerate(spec):
            if fname in named:
                fields[fname] = named[fname]
            elif i < len(positional):
                fields[fname] = positional[i]
            elif default is not None:
                fields[fname] = self.eval(default, self.globals)
            else:
                fields[fname] = NA
        return UDTInstance(type_name, fields)

    def call_user(self, name, positional, named, node):
        params, body = self.functions[name]
        scope = Scope(self.globals)
        for i, (pname, default) in enumerate(params):
            if pname in named:
                value = named[pname]
            elif i < len(positional):
                value = positional[i]
            elif default is not None:
                value = self.eval(default, self.globals)
            else:
                value = NA
            s = Series()
            s.set(value)
            scope.declare(pname, s)
        return self.exec_block(body, scope)

    def state_for(self, node):
        st = self.state.get(node.uid)
        if st is None:
            st = {}
            self.state[node.uid] = st
        return st

    def call_builtin(self, path, pos, named, node, scope):
        from .builtins import dispatch
        return dispatch(self, path, pos, named, node, scope)


# Strategy state under the no-execution model. Flat position, empty ledger.
STRATEGY_STATE = {
    "strategy.position_size": 0.0,
    "strategy.position_avg_price": NA,
    "strategy.opentrades": 0,
    "strategy.closedtrades": 0,
    "strategy.wintrades": 0,
    "strategy.losstrades": 0,
    "strategy.netprofit": 0.0,
    "strategy.grossprofit": 0.0,
    "strategy.grossloss": 0.0,
    "strategy.equity": 0.0,
    "strategy.initial_capital": 10000.0,
    "strategy.max_drawdown": 0.0,
    "strategy.openprofit": 0.0,
}


class Namespace:
    """A dotted path that is not a value — `math`, `array`, `ta.sma` before the
    call. Kept as an object so a typo produces a clear error at the call rather
    than an obscure one deeper in."""
    __slots__ = ("path",)

    def __init__(self, path):
        self.path = path

    def __repr__(self):
        return f"<ns {self.path}>"
