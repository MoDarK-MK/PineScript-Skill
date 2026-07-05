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
`default_qty_value`, or `commission_*` — leaving these at engine defaults
produces a backtest that doesn't reflect realistic trading costs.

### PINE022 — warning — `indicator()`/`strategy()` missing explicit `overlay=`
Cheap to set, avoids relying on the (version-dependent) engine default.

### PINE023 — info — `int`/`int` division of literals
```pinescript
// v6 returns 2.5 here; v5 truncated to 2 when both operands were const int
ratio = 5 / 2
```
Informational only — real scripts rarely divide two bare integer literals
on purpose, but if you do, and you want v5's truncation, wrap in `int(...)`.

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
