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

Note on numbering: there are 59 rules spanning codes PINE001–PINE060. The code
**PINE024 is intentionally unassigned** (a rule retired before release; the
number is kept vacant so existing suppression comments never change meaning).

PINE029–PINE035 only ever fire on strategies — they inspect `strategy.entry`/
`strategy.exit`/`strategy.order` calls, so an indicator can never trip them.
Design-level guidance for the patterns they enforce is in
`references/strategy-guide.md`.

PINE036–PINE041 cover visual quality and runtime cost. The reasoning behind them
is in `references/design-system.md` and `references/performance-guide.md`.

PINE042–PINE049 cover Pine's scope rules and platform limits — the ones that end
a paste with a compiler error rather than a bad-looking chart.

PINE050–PINE053 are the rules that needed more than pattern matching: the first
two are backed by a symbol table (what is declared, what is actually read), and
the last two cost a loop's worst case rather than counting its call sites.

Rules marked `[--fix]` by `--list-rules` can be repaired automatically with
`pine_lint.py FILE --fix` (add `--dry-run` to preview). A rule qualifies only
when there is exactly one correct rewrite — anything needing intent stays a
finding, because a linter that guesses is worse than one that nags.

## When TradingView gives you an error code

The linter is not a compiler, so this table is the bridge: look up the code
TradingView printed and see whether a rule already covers it. Every row here was
added *after* the error was hit in real use.

| TradingView error | Rule | What it means |
|---|---|---|
| `CE10088` Cannot modify global variable "x" in function | **PINE042** | A function assigned to a global |
| `CE10235` Return type of one of the if/switch blocks is not compatible | **PINE043** | Trailing if/else branches disagree on type |
| "This script uses seconds-based timeframes, which are only available to users with Premium…" | **PINE044** | A seconds resolution reached a non-Premium plan |
| *(no error — the feature is silently absent)* | **PINE045** | A guard compared against `na` and never matched |
| "Cannot use 'input' in local scope" | **PINE046** | `input.*()` called inside a function/if/loop |
| "Cannot use 'plot' in local scope" | **PINE047** | plot family called inside a function/if/loop |
| "The 'request' calls limit was exceeded" | **PINE048** | More than 40 unique `request.*()` calls |
| "Cannot use 'strategy.entry' in local scope" | **PINE049** | An order call inside a function |
| `Undeclared identifier 'x'` | **PINE050** | `:=` to a name that was never declared |
| *(no error — the drawings just vanish)* | **PINE052** | Drawings made in a loop with no `max_*_count` |
| "Loop takes too long to execute" / script timeout | **PINE053** | A loop nest whose worst case is unbounded |
| `Undeclared identifier "x"` / "cannot register side effect" | **PINE055** | A global declared BELOW the code that reads it |
| *(no error — the wrong value is simply used)* | **PINE058** | A name shadowing a built-in namespace, then dereferenced |
| *(no error — the array just accumulates)* | **PINE054** | A `var` collection grown on a tick with no confirmation guard |
| *(no error — the arithmetic is simply wrong)* | **PINE060** | Two ints divided where a fraction was wanted |
| "Missing enclosing character in the literal string" | **PINE059** | A string opened on a line that ends before closing it |
| `Pine cannot determine the referencing length…` | *(none yet)* | A dynamic history index without `max_bars_back` |

If you hit a code that is not in this table, that is a genuine gap — the fix is
to add a rule, not just to patch the script.

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

---

## Plan requirements (PINE044)

### PINE044 — info — Seconds-based timeframe
TradingView serves seconds-based timeframes **only to Premium and higher plans**,
and requesting one on a lower plan fails the **entire script**, not just that
call — the user sees "This script uses seconds-based timeframes, which are only
available to users with Premium and higher-tier plans" and nothing loads.

```pinescript
// risky as a default — breaks the script for most users
[o, c, v] = request.security_lower_tf(syminfo.tickerid, "1S", [open, close, volume])
```
```pinescript
// good — opt-in, defaulting off, with a minute-based fallback
bool allowSecondsInput = input.bool(false, "Allow Seconds-Based Intrabars")
resolveLtf(string mode, bool allowSeconds) =>
    str.endswith(mode, "S") and not allowSeconds ? "1" : mode
```

Advisory (info) rather than a warning because seconds data is a legitimate
choice when you know your audience has the plan — it just should never be the
silent default. Reported once per file.

---

## Silent-failure traps (PINE045)

### PINE045 — warning — `na` compared with `==` / `!=`
Pine does not compare reliably against `na`, so a test like `cachedBar != bar_index`
on a variable that starts as `na` **never matches on the first pass**. Nothing
errors; the guarded code simply never runs, and whatever it was supposed to draw
or compute is silently absent.

```pinescript
// bad — the scan never runs, so the profile never appears
var int cachedBar = na
if barstate.islast and cachedBar != bar_index
    cachedBar := bar_index
    rebuildProfile()
```
```pinescript
// good — na() handles the first pass explicitly
var int cachedBar = na
bool needsRebuild = na(cachedBar) or cachedBar != bar_index
if barstate.islast and needsRebuild
    cachedBar := bar_index
    rebuildProfile()
```

Fires only for variables declared `var x = na` and never passed to `na()`
anywhere in the file — if the file guards the variable properly even once, the
rule stays quiet.

---

## Scope and platform limits (PINE046–PINE049)

Pine restricts several call families to global scope. The compiler messages name
the function but not the line that caused it, which is why these are worth
catching locally.

### PINE046 — error — `input.*()` outside global scope
```pinescript
// bad — "Cannot use 'input' in local scope"
getLength() =>
    input.int(14, "Length")
```
```pinescript
// good — declare at the top level, pass the value in
int lengthInput = input.int(14, "Length")
getLength(int n) => n
```

### PINE047 — error — plot family outside global scope
Covers `plot`, `plotshape`, `plotchar`, `plotarrow`, `plotbar`, `plotcandle`,
`bgcolor`, `barcolor`, `fill`, `hline` and `alertcondition`.
```pinescript
// bad — the usual mistake: making a plot conditional by wrapping it
if showMa
    plot(maValue, "MA")
```
```pinescript
// good — keep the call global and feed it na
plot(showMa ? maValue : na, "MA")
```
Note that `line.new`, `label.new` and `box.new` are NOT restricted this way and
are perfectly fine inside an `if` — the rule does not flag them.

### PINE048 — warning — Approaching/over the 40 `request.*()` limit
TradingView caps a script at **40 unique** `request.*()` calls (64 on Ultimate).
Identical calls reuse one series, so this counts *distinct argument lists*,
which is what actually consumes the budget. Configurable via `.pine-lint.json`'s
`max_requests` and `request_warn_ratio`.

### PINE049 — error — `strategy.*()` order call inside a function
```pinescript
// bad — "Cannot use 'strategy.entry' in local scope"
tryEnter(bool go) =>
    if go
        strategy.entry("Long", strategy.long)
```
```pinescript
// good — decide in the function, order at global scope
shouldEnter(bool go) => go and barstate.isconfirmed
if shouldEnter(signal)
    strategy.entry("Long", strategy.long)
```

---

## Symbol-table and cost rules (PINE050–PINE053)

### PINE050 — error — Reassignment with `:=` to a name that is never declared
Pine answers this with `Undeclared identifier`. It is almost always a typo in
the target name, which is exactly the case a text-matching linter cannot see:
the misspelled name looks like perfectly ordinary code on its own line.
```pinescript
// bad — declared as `atrLen`, assigned as `atrLenght`
atrLen = 14
if timeframe.isdaily
    atrLenght := 21
```
```pinescript
// good
var atrLen = 14
if timeframe.isdaily
    atrLen := 21
```
Names declared anywhere in the file count, including function parameters and
loop variables, so the rule fires only when nothing plausible was declared at
all.

### PINE051 — info — Variable declared but never read
Two different defects share this shape. One is a leftover from a feature that
was deleted around it. The other is a **write-only** variable: something is
computed and stored on every bar and nothing ever looks at it, which costs
runtime and misleads the next reader into thinking it matters.
```pinescript
// bad — the value is produced and immediately abandoned
dropped = array.shift(swings)
```
```pinescript
// good — the call still runs, without pretending the result is used
array.shift(swings)
```
Names starting with `_` are exempt, that being the conventional way to say "I
know, I am discarding this". Reference snippets that exist to be copied out of
can suppress the rule file-wide.

### PINE052 — warning — Drawing created inside a loop without the matching `max_*_count`
PINE025 counts call *sites*, which is the wrong unit as soon as the drawings are
created in a loop: one `box.new()` inside a pool loop can allocate hundreds.
Without `max_boxes_count` the declaration defaults to **50**, and TradingView
keeps only the newest 50 with no error at all — the chart is simply missing its
older drawings.
```pinescript
// bad — pool of up to 300 boxes, declared limit is the default 50
indicator("VP", overlay = true)
for i = 0 to rowsInput - 1
    array.push(pool, box.new(bar_index, close, bar_index, close))
```
```pinescript
// good
indicator("VP", overlay = true, max_boxes_count = 500)
```

### PINE053 — warning — Loop nest's worst-case iteration count is over budget
Pine aborts a loop that runs longer than 500 ms and a script that runs longer
than 20 s. Both limits are reached by multiplication: an outer bound and an
inner bound that are each perfectly reasonable alone. The worst case is what a
user reaches by turning an input up to its `maxval`, so that is what gets
costed — a bound the linter cannot resolve is reported as nothing at all rather
than guessed at.
```pinescript
// bad — 5000 x 500 = 2,500,000 iterations at the inputs' maximums
lookback = input.int(300, "Bars", maxval = 5000)
rows     = input.int(30,  "Rows", maxval = 500)
for i = 0 to lookback
    for r = 0 to rows
        array.set(buf, r, array.get(buf, r) + volume[i])
```
```pinescript
// good — the inner loop only touches the rows the bar actually spans
for i = 0 to lookback
    for r = startIdx to endIdx
        array.set(buf, r, array.get(buf, r) + perRow
```
Sibling loops are additive, not multiplicative, so only the heaviest nested
chain multiplies the outer bound.

### PINE054 — warning — `var` collection grown with no bar-confirmation guard
`var` restores the VARIABLE on a realtime rollback. It never restores the
contents of the object that variable points at. So a `push` onto a `var` array,
made on a tick, is permanent — even when the condition that caused it turns out
to be false later in the same bar.

The conditions this bites are the common ones: `ta.pivothigh`'s window includes
the bar still forming, and any "close broke the level" test reads a `close` that
moves all bar. There is no error message. The array just accumulates entries for
things that never finished.
```pinescript
// bad — a pivot that appears mid-bar and vanishes still leaves its entry
var array<float> levels = array.new<float>()
float ph = ta.pivothigh(high, 5, 5)
if not na(ph)
    array.push(levels, ph)
```
```pinescript
// good — record when the bar that confirms it actually closes
var array<float> levels = array.new<float>()
float ph = ta.pivothigh(high, 5, 5)
if not na(ph) and barstate.isconfirmed
    array.push(levels, ph)
```
Growing a DRAWING pool is exempt: `while array.size(pool) < needed` converges
instead of accumulating, so an unguarded `array.push(pool, box.new(...))` is
correct and the rule does not fire on it.

### PINE055 — error — Function references a global declared later in the file
Pine resolves identifiers in TEXTUAL order. A function body can only see what
was declared above its own declaration, so reading a global declared further
down the file is `Undeclared identifier` at compile time — and the error points
at the function, which is the one place the problem is not.

This is easy to create by accident. Adding a `request.*` call in the
calculations section and then reading it from a helper that happens to sit
higher up looks perfectly reasonable in a diff, and the file still reads top to
bottom in a sensible order.
```pinescript
// bad — "Undeclared identifier ltfVolume", reported against the function
sumIntrabar(int barsBack) =>
    array<float> v = ltfVolume[barsBack]
    na(v) ? 0.0 : array.sum(v)

array<float> ltfVolume = request.security_lower_tf(syminfo.tickerid, "1", volume)
```
```pinescript
// good — the declaration moves above every function that reads it
array<float> ltfVolume = request.security_lower_tf(syminfo.tickerid, "1", volume)

sumIntrabar(int barsBack) =>
    array<float> v = ltfVolume[barsBack]
    na(v) ? 0.0 : array.sum(v)
```
Parameters, loop variables and anything the function declares itself are not
forward references and are never flagged.

The rule originally walked only function bodies, and missed the version that shipped from this repo: two counters declared with the drawing pools and incremented from a top-level `if` several hundred lines earlier. Textual resolution is not a property of functions — it applies everywhere, so the rule now checks global blocks too.

### PINE056 — info — Function declared but never called
Pine has no dead-code warning of its own, so an orphaned helper survives every
refactor that meant to remove it — and goes on being read, maintained and kept
compiling for nothing.
```pinescript
// bad — nothing calls this any more
formatOldLabel(float v) =>
    str.tostring(v, "#.##") + " units"
```
`export`ed library functions are exempt: being uncalled inside the library is
the normal case for them. A file of reference snippets can opt out file-wide
with `// pine-lint-disable PINE056`, which is what this repo's
`references/snippets/` do.

### PINE057 — warning — Condition is constant
A condition whose value cannot change. All three shapes below compile, none is
reported by TradingView, and each silently disables or permanently enables the
block under it.
```pinescript
// bad — a debug switch someone forgot
if true
    label.new(bar_index, high, "debug")

// bad — a half-finished edit
if 2 > 1
    doSomething()

// bad — almost always a typo for a different variable, and NOT an na check
if value == value
    doSomething()
```
```pinescript
// good — and if you meant "is this na", say so
if na(value)
    doSomething()
```

### PINE058 — error — Name shadows a built-in namespace
A parameter or variable named after a built-in namespace (`format`, `label`,
`color`, `math`, `str`, …) shadows it inside that scope. The rule fires only
when the shadow is also DEREFERENCED — `name.something` — because that is when
it does damage, and flagging every `string label` would make the rule noise.

Nothing errors when it happens. Passing the wrong thing to a function that
accepts it is legal, so the damage surfaces as wrong output rather than a
compile failure.
```pinescript
// bad — `format.mintick` reads the PARAMETER, a string
payload(float price, string format) =>
    str.tostring(price, format.mintick)
```
```pinescript
// good
payload(float price, string style) =>
    str.tostring(price, format.mintick)
```
This shipped in this repo, and was found by EXECUTING the script offline rather
than by reading it — see `scripts/pine_interp/`.

### PINE059 — error — String literal not closed on its own line
Pine has no multi-line string. A quote that opens on a line which ends before
closing it is a hard compile failure:

> Error at 430:1 Missing enclosing character in the literal string. Enclose
> literal strings using a set of quotation marks (") or apostrophes (') on the
> same code line.

Almost nobody writes this deliberately. It arrives when a tool rewrites the
file and turns an escape sequence into a real newline, splitting one string
into two that never close:
```pinescript
// bad — the \n became an actual line break, so neither half closes
tooltip="How far ahead a node must be." +
"

Without a floor the nearest busy row is the one right next to it."
```
```pinescript
// good
tooltip="How far ahead a node must be." +
     "\n\nWithout a floor the nearest busy row is the one right next to it."
```
This shipped twice from this repo. Both times the file linted clean first,
because bracket counting can stay balanced across the break — the opening
paren is still matched, so nothing looked wrong until TradingView read it.

The interpreter rejects it too. It used to accept it: wrapped lines are joined
before tokenising, so the string simply closed on a later line and the script
ran. An interpreter that accepts what TradingView rejects is worse than one
that refuses to read the file, so it now refuses.

### PINE060 — error — Integer division used where a fraction was wanted
Pine divides two integers as an **integer**. `30 / 14` is `2`, not `2.142`, so
a fraction written that way is truncated before anything else sees it.

Two shapes are reported, both meaning the author expected a fraction:
```pinescript
// bad — ceil() of a value that is already an integer
int stride = int(math.ceil(rows / affordable))
float ratio = rows / affordable
```
```pinescript
// good — one side forced to float first
int stride = int(math.ceil(rows * 1.0 / affordable))
float ratio = rows * 1.0 / affordable
```
Rounding an integer is a no-op, and that is what makes this rule able to be
certain rather than merely suspicious. Integer division INTO an int —
`int half = total / 2` — is legitimate and is not reported.

This shipped from this repo and was reported from a chart three separate times.
A bucket stride computed as `math.ceil(rows / affordable)` came out one short
whenever the two did not divide evenly, so the profile needed more boxes than
it had been granted and the loop drawing it broke early — removing the top of
every profile. Measured with the fault present: **94.1% of the price span
covered at 100 rows, 97.0% at 500**.

It was invisible twice over. The source reads correctly, and the offline
interpreter divided the way arithmetic does rather than the way Pine does, so
every test agreed with the broken script. `scripts/pine_interp/` now truncates
integer division and carries declared types so it can tell an int from a float.
An interpreter that is more forgiving than the platform does not merely miss
bugs — it vouches for them.


