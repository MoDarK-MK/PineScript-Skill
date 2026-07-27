# Lint Rule Catalog

Generated against `scripts/pine_lint.py`'s `RULES` dict — run
`python3 scripts/pine_lint.py --list-rules` to print the current authoritative
list (codes/severities here must match it). Every rule below is either a
mechanical certainty (a documented v6 compile error) or a well-established
style/correctness convention — none are guesses.

Severity meanings: **error** = will very likely fail to compile or is a
guaranteed-wrong pattern. **warning** = compiles, but is very likely a bug or
against documented best practice. **info** = a behavior difference worth
knowing, not a problem to fix.

Suppress any rule with `// pine-lint-disable-next-line CODE`,
`// pine-lint-disable-line CODE`, or file-wide with a top-of-file
`// pine-lint-disable CODE1,CODE2`.

Note on numbering: there are 42 rules spanning codes PINE001–PINE043. The code
**PINE024 is intentionally unassigned** (a rule retired before release; the
number is kept vacant so existing suppression comments never change meaning).

PINE029–PINE035 only ever fire on strategies — they inspect `strategy.entry`/
`strategy.exit`/`strategy.order` calls, so an indicator can never trip them.
Design-level guidance for the patterns they enforce is in
`references/strategy-guide.md`.

PINE036–PINE041 cover visual quality and runtime cost. The reasoning behind them
is in `references/design-system.md` and `references/performance-guide.md`.

---

### PINE001 — error — Missing or malformed `//@version=` pragma
No `//@version=N` annotation found anywhere in the file. Without it Pine
silently assumes v1, which disables all modern syntax.
```pinescript
// bad: no version pragma at all
indicator("X")
```
```pinescript
// good
//@version=6
indicator("X")
```

### PINE002 — error — No `indicator()`/`strategy()`/`library()` declaration
Every script needs exactly one of these three declaration calls.

### PINE003 — error — Unbalanced parentheses or brackets
Self-explanatory structural check across the whole file.

### PINE004 — error — Deprecated `study()`/`security()` syntax
Both were renamed years ago (`study()` → `indicator()`, `security()` →
`request.security()`) and are compile errors now, not just deprecated.

### PINE005 — warning — Accumulator reassigned without `var`
```pinescript
// bad: resets to 0 every single bar, never actually accumulates
total = total + volume
```
```pinescript
// good
var float total = 0.0
total := total + volume
```

### PINE006 — warning — `request.security()` without explicit `lookahead=`
Not wrong by default, but worth a second look — the most common source of
repainting on TradingView. `lookahead=barmerge.lookahead_off` is what you want
for a signal that shouldn't repaint.

### PINE007 — warning — `input.*()` call missing a title
```pinescript
// bad
lengthInput = input.int(14)
```
```pinescript
// good — title can be positional or named, both are fine
lengthInput = input.int(14, "Length")
```
Note: this rule looks for *any* quoted string in the call as a heuristic
(titles are usually positional, not `title=`), so it won't false-positive on
normal calls — but it can occasionally miss a genuinely missing title if the
only string present is inside `options=[...]`.

### PINE008 — warning — Line exceeds configured max length (default 120)
Configurable via `.pine-lint.json`'s `max_line_length`. Wrap long calls in
parens per `references/style-guide.md` rather than suppressing this.

### PINE009 — warning — Approaching/over the 64 plot-count limit
Counts calls to `plot`, `plotarrow`, `plotbar`, `plotcandle`, `plotchar`,
`plotshape`, `alertcondition`, `bgcolor`, `barcolor`, `fill` — the functions
that share the real 64-item cap. This is a **lower-bound estimate**: some
calls consume up to 7 plot-counts each depending on how many arguments are
dynamic. See `references/pine-v6-guide.md` §6 for the exact weighting.

### PINE010 — error — `when=` parameter (removed in v6)
```pinescript
// bad — compile error in v6
strategy.entry("Long", strategy.long, when=longCondition)
```
```pinescript
// good
if longCondition
    strategy.entry("Long", strategy.long)
```

### PINE011 — error — `transp=` parameter (removed in v6)
```pinescript
// bad — compile error in v6
plot(close, color=color.blue, transp=50)
```
```pinescript
// good
plot(close, color=color.new(color.blue, 50))
```

### PINE012 — error — `linewidth` below the v6 minimum of 1
```pinescript
// bad — compile error in v6 (v5 silently clamped this to 1 visually)
plot(close, linewidth=0)
```

### PINE013 — error — `switch` missing a default `=>` arm
```pinescript
// bad — compile error in v6 (v5 allowed omitting the default)
x = switch dayOfWeek
    1 => "Mon"
    2 => "Tue"
```
```pinescript
// good
x = switch dayOfWeek
    1 => "Mon"
    2 => "Tue"
    => "Other"
```

### PINE014 — error — History-referencing `[]` on a literal/constant
```pinescript
// bad — compile error in v6; [] only works on variables/series now
plot(6[1])
bgcolor(true[10] ? color.orange : na)
```

### PINE015 — error — Same named parameter repeated in one call
```pinescript
// bad — v5 warned and used the first value; v6 is a compile error
plot(close, color=color.blue, linewidth=2, color=color.red)
```

### PINE016 — warning — `timeframe.period` compared to a bare unit string
```pinescript
// bad — will basically never match in v6
isDaily = timeframe.period == "D"
```
```pinescript
// good — v6 always includes the multiplier
isDaily = timeframe.period == "1D"
```

### PINE017 — warning — Possible v6 lazy `and`/`or` evaluation trap
```pinescript
// risky — ta.rsi() may not run every bar under short-circuit evaluation,
// which can corrupt its internal state
signal = close > open and ta.rsi(close, 14) > 50
```
```pinescript
// safer — compute the ta.* call unconditionally, then use it in the condition
float rsiValue = ta.rsi(close, 14)
signal = close > open and rsiValue > 50
```

### PINE018 — warning — Identifier doesn't follow camelCase/SNAKE_CASE
Style-only, per `references/style-guide.md`: variables `camelCase`, constants
`SNAKE_CASE`. Only checks each statement's own declaration line (not named
arguments inside a wrapped call, which look similar but aren't declarations).

### PINE019 — error — Mixed tabs and spaces within one line's indentation
A single line whose leading whitespace mixes ` ` and `\t` — Pine's block
structure depends on indentation, so this is a near-guaranteed structural bug.

### PINE020 — error — Block header with no indented body following
```pinescript
// bad — dangling if with nothing indented below it
if close > open

plot(close)
```
Covers `if`/`for`/`while`/`else`/`switch` and a trailing `=>` (function/method
definitions and multi-line switch arms) — Pine has no same-line-body syntax
for any of these, so a header must always be followed by a more-indented line.

### PINE021 — warning — `strategy()` missing recommended sizing/commission params
Flags a `strategy()` declaration that doesn't set `default_qty_type`,
`default_qty_value`, `commission_*`, `initial_capital`, or `slippage` — leaving
these at engine defaults produces a backtest that doesn't reflect realistic
trading costs, and `initial_capital`/`slippage` change every number the Strategy
Tester reports, so an implicit value means the published backtest isn't
reproducible.

The check inspects the `strategy()` **call itself**, not the whole file, so a
parameter merely mentioned in a comment no longer satisfies it.

### PINE022 — warning — `indicator()`/`strategy()` missing explicit `overlay=`
Cheap to set, avoids relying on the (version-dependent) engine default. Like
PINE021, the check inspects the declaration **call** rather than the whole file,
so a mention of `overlay=` in a comment no longer satisfies it.

### PINE023 — info — `int`/`int` division of literals
```pinescript
// v6 returns 2.5 here; v5 truncated to 2 when both operands were const int
ratio = 5 / 2
```
Informational only — real scripts rarely divide two bare integer literals
on purpose, but if you do, and you want v5's truncation, wrap in `int(...)`.

*(PINE024 intentionally unassigned — see the numbering note at the top.)*

### PINE025 — warning — Approaching/over line/box/label/polyline/table limits
Separate pools from PINE009: `line.new`/`box.new`/`label.new` cap at 500 IDs
(only the last 50 shown by default — set `max_lines_count` etc. to raise the
display cap), `polyline.new` caps at 100, and only 9 tables can be on the
chart at once (one per `position.*` slot).

### PINE026 — warning — File mixes tab-indented and space-indented lines
Different from PINE019 (which is about mixing *within one line*) — this is
about the file using tabs in some places and spaces in others. Fragile even
if each individual block is internally consistent; pick one.

### PINE027 — error — `indicator()`/`strategy()` has no output-producing call
```pinescript
// bad — compiles to nothing useful, and current docs confirm this errors
indicator("X")
x = close + open
```
Indicators need at least one of `plot`/`plotshape`/`barcolor`/`line.new`/
`log.info`/`alert`/etc.; strategies also accept `strategy.entry`/`order`/
`close`/`exit`.

### PINE028 — warning — Real code appears before the `//@version=` pragma
Syntactically legal (TradingView's own docs confirm the annotation can go
anywhere), but their style guide recommends it at the top, right after any
license comment, for readability.

---

## Strategy rules (PINE029–PINE035)

These only fire on scripts that call `strategy.entry`/`strategy.exit`/
`strategy.order`. See `references/strategy-guide.md` for the design reasoning
behind each one.

### PINE029 — error — `strategy.exit()` with no level
```pinescript
// bad — places no order at all: the position has no stop and no target
strategy.exit("Long Exit", "Long")
```
```pinescript
// good
strategy.exit("Long Exit", "Long", stop=stopPrice, limit=targetPrice)
```
An exit command whose `stop`/`loss`/`limit`/`profit`/`trail_price`/`trail_points`
arguments are all absent does nothing. This is the most common way a strategy
silently ends up with no risk management at all.

### PINE030 — warning — Relative and absolute level for the same exit type
```pinescript
// bad — v5 used the absolute level; v6 uses whichever triggers FIRST
strategy.exit("X", "Long", stop=stopPrice, loss=20)
```
The pairs are `(profit, limit)`, `(loss, stop)`, and `(trail_points, trail_price)`.
Set exactly one of each pair. This is the mechanical check for the v6 semantic
change documented in `pine-v6-guide.md` §2 row 8 — a ported v5 strategy exits
differently now.

### PINE031 — warning — Tick parameter given a price expression
```pinescript
// bad — trail_offset is in TICKS, so this is off by 1/syminfo.mintick
strategy.exit("X", "Long", trail_price=p, trail_offset=atrValue * 2)
```
```pinescript
// good
strategy.exit("X", "Long", trail_price=p, trail_offset=int(atrValue * 2 / syminfo.mintick))
```
`loss`, `profit`, `trail_points`, and `trail_offset` are denominated in ticks;
`stop`, `limit`, and `trail_price` are in price. A bare integer literal or an
expression mentioning `syminfo.mintick`/`syminfo.pointvalue` is accepted. This is
a heuristic, so it's a suppressible warning.

### PINE032 — warning — Unguarded `strategy.position_avg_price`
While the strategy is flat, `strategy.position_avg_price` is `na`, so a stop or
target derived from it is `na` on those bars and the resulting exit places
nothing. Guard the block with `strategy.position_size > 0` / `< 0` /
`strategy.opentrades`, or `na()`-check the value. File-level check: one guard
anywhere in the file satisfies it.

### PINE033 — error — `qty=`/`qty_percent=` literal out of range
`qty` must be positive; `qty_percent` must be within `0 < x <= 100`. Only
literal values are checked, so a computed `qty=positionQty(...)` is never
flagged.

### PINE034 — error — `from_entry` names a nonexistent entry id
```pinescript
strategy.entry("Long", strategy.long)
strategy.exit("X", "Lonng", stop=s)     // typo — attaches to nothing, never fires
```
The check is skipped entirely when any entry id is a computed expression rather
than a string literal, since ids can legitimately be built at runtime.

### PINE035 — warning — Entries with no exit mechanism
A strategy that calls `strategy.entry`/`strategy.order` but never
`strategy.exit`, `strategy.close`, `strategy.close_all`, or a `strategy.risk.*`
rule only closes positions via an opposite entry — no trade has a defined risk.

---

## Visual & performance rules (PINE036–PINE041)

See `references/design-system.md` and `references/performance-guide.md`.

### PINE036 — error — Table cell without `text_color=`
```pinescript
// bad — Pine defaults cell text to BLACK, invisible on a dark panel
t.cell(1, 1, str.tostring(maValue, "#.##"), text_size=size.small)
```
```pinescript
// good
t.cell(1, 1, str.tostring(maValue, format.mintick), text_color=textColor, text_size=size.small)
```
Both call forms are checked: `table.cell(id, col, row, text, …)` and the method
form `myTable.cell(col, row, text, …)`. A cell whose text is an empty string
literal is treated as a deliberate spacer and skipped.

This is error severity because it is silent, extremely common, and looks fine to
whoever wrote it on a light chart. The reliable fix is a row builder that takes
the colors as required arguments — see `references/snippets/table_helpers.pine`.

### PINE037 — warning — `array.new` in a per-bar block without `var`
```pinescript
// bad — reallocated on every realtime tick
if barstate.islast
    array<float> bins = array.new<float>(24, 0.0)
```
```pinescript
// good — one buffer, cleared in place
var array<float> bins = array.new<float>(24, 0.0)
if barstate.islast
    array.fill(bins, 0.0)
```
A temporary inside a user function body is exempt — that is an ordinary local,
not per-bar churn.

### PINE038 — warning — Drawing churn inside a `barstate` guard
Deleting and recreating drawings on every tick costs N destructions plus N
allocations and makes them visibly flicker.
```pinescript
// bad
if barstate.islast
    line.delete(myLine)
    myLine := line.new(x1, y, x2, y)
```
```pinescript
// good — create once, then move
if barstate.islast
    line.set_xy1(myLine, x1, y)
    line.set_xy2(myLine, x2, y)
```

### PINE039 — warning — Duplicate `request.security()`
Two calls sharing symbol, timeframe and lookahead each instantiate a separate
higher-timeframe series. Return a tuple from one call instead.
```pinescript
// bad — two HTF evaluations
[pdh, pdl] = request.security(syminfo.tickerid, "D", [high[1], low[1]], lookahead=barmerge.lookahead_on)
float dayOpen = request.security(syminfo.tickerid, "D", open, lookahead=barmerge.lookahead_on)
```
```pinescript
// good — one
[pdh, pdl, dayOpen] = request.security(
     syminfo.tickerid, "D", [high[1], low[1], open], lookahead=barmerge.lookahead_on)
```

### PINE040 — warning — `plot()` without a title
The mirror of PINE007 for inputs. An untitled plot appears unnamed in the
settings panel, data window and status line. A positional second-argument string
or `title=` both satisfy it.

### PINE041 — warning — `size.large` / `size.huge`
`references/design-system.md` §2 caps chart text at `size.normal`; larger sizes
clip or wrap at real panel widths.

---

## Function-scope compile errors (PINE042–PINE043)

Two hard TradingView compile errors that nothing else here catches, and that
both hide inside the same idiom — a helper that tallies assertions.

### PINE042 — error — Function assigns to a global variable
Pine forbids a function from modifying a variable declared at global scope.
TradingView rejects it as **CE10088**.
```pinescript
// bad — "Cannot modify global variable 'passCount' in function"
var int passCount = 0
recordAssertion(bool condition) =>
    if condition
        passCount += 1
```
```pinescript
// good — return the value, let the caller apply it
var int passCount = 0
assertFailed(bool condition) =>
    condition ? 0 : 1

if testModeInput
    int fails = 0
    fails += assertFailed(someCheck)
    passCount += TEST_COUNT - fails
```
Mutating a **parameter** is fine — arrays and user-defined-type objects are
passed by reference, so `array.push(arr, x)` and `obj.field := x` inside a
function are both legal and are not flagged. Mutating a global **outside** a
function is also fine.

### PINE043 — error — Trailing `if`/`else` branches return different types
When an `if`/`else` is a function's last statement it becomes the return value,
so both branches must yield the same type. TradingView rejects a mismatch as
**CE10235**.
```pinescript
// bad — "series int" from one branch, "series label" from the other
record(bool ok, string msg) =>
    int n = 0
    if ok
        n := n + 1
    else
        label.new(bar_index, high, msg)
```
```pinescript
// good — end the function on one plain expression
record(bool ok, string msg) =>
    if not ok
        label.new(bar_index, high, msg)
    ok ? 0 : 1
```
The check is deliberately narrow: it fires only when the trailing `if`/`else`
has one branch ending in an assignment and the other in a `.new()` constructor,
which is the shape that actually occurs.
