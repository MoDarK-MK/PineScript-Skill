# Pine Script v6 Reference Guide

Everything here is fact-checked against TradingView's official docs (pine-script-docs
migration guide, limitations page, style guide) as of mid-2026. Where TradingView
could plausibly change a number in the future (limits especially), that's noted —
re-verify with a web search if a script is right up against a limit and the behavior
seems off, since Pine gets monthly updates.

## Table of contents
1. Version pragma & script structure
2. Breaking changes from v5 (things that now error or behave differently)
3. Dynamic requests (request.*() in v6)
4. Repainting traps
5. var / varip semantics
6. Hard platform limits (verified numbers)
7. Strategy-specific notes
8. Things v6 relaxed (no longer errors)

---

## 1. Version pragma & script structure

`//@version=6` must be the literal first line. Follow the section order in
`references/style-guide.md` (license → version → declaration → imports → constants
→ inputs → functions → calculations → strategy calls → visuals → alerts).

```pinescript
//@version=6
indicator("My Indicator", shorttitle="MI", overlay=true)
```
```pinescript
//@version=6
strategy("My Strategy", overlay=true, default_qty_type=strategy.percent_of_equity,
     default_qty_value=10, initial_capital=10000, commission_type=strategy.commission.percent,
     commission_value=0.05, margin_long=100, margin_short=100)
```

Always set explicit `overlay=`. For strategies, always set `default_qty_type`,
`default_qty_value`, `commission_*`, and `initial_capital` explicitly — leaving
these at engine defaults produces backtest results that don't reflect realistic
trading conditions (see `references/publishing-guide.md` for TradingView's realism
expectations if the user plans to publish it).

## 2. Breaking changes from v5 (each of these is a real compile error or silent
behavior change — the linter checks the mechanical ones automatically)

| # | Change | Linter rule |
|---|---|---|
| 1 | `int`/`float` no longer implicitly cast to `bool` — `if bar_index` is invalid, must be `if bar_index != 0` or wrap with `bool()` | not auto-checkable (needs type inference); watch for bare numeric identifiers used directly as an `if`/ternary condition |
| 2 | `bool` can never be `na` anymore; `na()`, `nz()`, `fixnan()` no longer accept bool args | not auto-checkable |
| 3 | `and`/`or` now evaluate **lazily** (short-circuit) | PINE017 flags a likely trap: a `ta.*()`/`request.*()` call as the non-first operand of `and`/`or` inside a condition |
| 4 | `switch` **must** include a `default =>` arm (v5 allowed omitting it) | PINE013 |
| 5 | `if`-as-expression assigning a "unique type" (e.g. `plot.style_*`) must have an `else` branch, same reason as #4 | not auto-checkable generically |
| 6 | The `when=` parameter is **removed** from `strategy.entry/order/exit/close/close_all/cancel/cancel_all` — wrap the call in `if` instead | PINE010 |
| 7 | Default `margin_long`/`margin_short` for strategies changed from `0` to `100` — v6 strategies respect available funds and issue margin calls by default | informational, part of PINE_DECL check |
| 8 | `strategy.exit()` now uses whichever of the relative (`profit`/`loss`/`trail_points`) or absolute (`limit`/`stop`/`trail_price`) level triggers **first**, instead of v5's "absolute always wins" | not auto-checkable (semantic) — documented here so you know to re-verify exits after porting a v5 strategy |
| 9 | History-referencing operator `[]` can no longer be used on **literals** or built-in constants (`6[1]`, `true[1]`, `color.red[2]`, `"str"[1]`) | PINE014 |
| 10 | `[]` can no longer be used directly on a **field** of a user-defined-type object — wrap the object reference in parens first: `(myObj[10]).field`, not `myObj.field[10]` | not auto-checkable reliably (regex can't distinguish UDT fields from namespace calls) — watch for this manually when using UDTs |
| 11 | A function call can no longer repeat the same named parameter twice (was a warning in v5, now a compile error) | PINE015 |
| 12 | The `offset` parameter of `plot()` and similar functions no longer accepts "series" values, only "simple" or weaker | not auto-checkable (needs qualifier inference) |
| 13 | Minimum `linewidth` is now 1 (v5 silently clamped smaller values visually but still compiled) | PINE012 |
| 14 | The `transp` parameter is **completely removed** from `bgcolor()`, `fill()`, `plot()`, `plotarrow()`, `plotchar()`, `plotshape()` — use `color.new(color, transparency)` instead | PINE011 |
| 15 | `timeframe.period` always includes a multiplier now (`"1D"` not `"D"`) — comparisons like `timeframe.period == "D"` will never match | PINE016 |
| 16 | `for` loops now re-evaluate their end boundary (`to_num`) **before every iteration**, not once before the loop starts — a v5 loop whose bound depends on a value mutated inside the loop body can behave very differently (even loop forever) after conversion | not auto-checkable (needs data-flow analysis) — flagged in this guide only |
| 17 | Division of two `const int` literals can now return a fractional result (`5/2` → `2.5`, not `2`) | PINE023 (info-level note only, not a warning — very low real-world impact) |

## 3. Dynamic requests (`request.*()` in v6)

This is the single biggest structural change and it's the *opposite* of the old
"always keep request.security() at global scope" advice:

- In v6, **dynamic requests are on by default**. `request.*()` calls can now:
  - Use "series string" arguments for symbol/timeframe (change what they request
    on any historical bar)
  - Be called from inside loops, conditional structures, and even exported
    library functions
- If you explicitly set `dynamic_requests = false` in the `indicator()`/
  `strategy()`/`library()` declaration to replicate old v5 behavior, then calling
  `request.*()` from a local scope becomes a **compile error** again.
- Practical guidance: leave `dynamic_requests` at its default (don't set it to
  `false`) unless you have a specific reason to lock down the request context, and
  you're then free to write more natural, DRY code that calls `request.security()`
  once inside a loop over a symbol list, rather than one call per symbol.

This does **not** eliminate repainting concerns — a `request.security()` call still
needs `lookahead=barmerge.lookahead_off` (or no `lookahead` argument, which defaults
to off-equivalent behavior for confirmed bars) to avoid pulling in data that wasn't
actually available yet. PINE006 still checks for this.

## 4. Repainting traps

- `request.security()` on a higher timeframe **without** confirming the request is
  looking only at closed bars is the most common repaint source. PINE006 flags any
  `request.security()` call missing an explicit `lookahead=` argument.
- Using the current (unclosed) bar's `close` for a signal that later changes value
  on bar close. Gate signals meant to be "final" with `barstate.isconfirmed` or
  reference `[1]` (previous, closed bar).
- `ta.pivothigh()`/`ta.pivotlow()` only confirm a pivot N bars *after* it happened —
  a naive plot will look like it "predicted" the pivot on a replay/backtest when it
  couldn't have in real time. Mention this explicitly if a script uses pivots for
  signals.

## 5. `var` / `varip` semantics

- `var x = expr` initializes once (bar 0 or first execution) and persists across
  bars — for running counters/accumulators, not per-bar recalculated values.
- `varip` also persists across realtime intrabar ticks — rarely needed; mostly for
  alert/state machines that must survive intrabar updates. Reaching for `varip`
  without a specific intrabar-persistence requirement is a common source of
  confusing double-fired alerts.
- Forgetting `var` on an accumulator (`total = total + x`) resets it every bar — the
  single most common beginner bug. PINE005 flags this pattern.
- The style guide explicitly says: do **not** use `var` for constants — it adds
  needless per-bar maintenance for a value that never changes anyway.

## 6. Hard platform limits (verified against the official Limitations page)

These are real, enforced numbers — not estimates:

- **Plot count**: max **64** "plot counts" per script. The functions that consume
  plot counts are `plot()`, `plotarrow()`, `plotbar()`, `plotcandle()`,
  `plotchar()`, `plotshape()`, `alertcondition()`, `bgcolor()`, `barcolor()`, and
  `fill()` (only if its `color` argument is a "series" — i.e. computed/dynamic —
  value). **One call can consume up to 7 plot counts** depending on how many of its
  arguments are dynamic (e.g. `plotcandle()` with dynamic `color`, `wickcolor`, and
  `bordercolor` all set costs 7). `hline()`, `line.new()`, `label.new()`,
  `table.new()`, and `box.new()` do **not** count toward this limit at all — they
  have their own separate limits below. PINE009 gives an approximate lower-bound
  count; treat it as a floor, not an exact count, since exact counting needs to know
  which arguments are "series" vs "simple/const".
- **Lines, boxes, labels**: max **500** IDs each (raise via `max_lines_count`,
  `max_boxes_count`, `max_labels_count` in the declaration), but only the **last 50**
  show on the chart by default. Setting a drawing's property to `na` still counts it
  toward the total — delete/skip creating it instead of nulling its position if you
  need to stay under a cap.
- **Polylines**: max **100** IDs (`max_polylines_count`).
- **Tables**: max **9** on the chart — one per `position.*` slot. Two tables at the
  same position → only the newest shows.
- **`request.*()` calls**: max **40 unique** calls (**64** on the Ultimate plan).
  Identical repeated calls (same function, same arguments) reuse the first call's
  data and don't count again — only genuinely distinct calls count. Library-imported
  `request.*()` calls count too.
- **Execution time**: 20 seconds total for Basic-plan accounts, 40 seconds for other
  plans. Any single loop is capped at 500ms per bar. Compilation itself is capped at
  2 minutes (3 consecutive timeouts → a 1-hour compile ban).
- **Compiled size**: 100,000 tokens per script (not characters/lines — post-
  optimization tokens), or 1,000,000 total if importing libraries.
- **Variables per scope**: 1,000 max in any single scope (global or local).
- **History buffer (`[]` lookback)**: 5,000 bars for most series, but **10,000**
  bars for `open`/`high`/`low`/`close`/`time`. Adjustable via `max_bars_back()` or
  the `max_bars_back` declaration parameter if you hit the error.
- **Forward-projected drawings** (`xloc.bar_index` beyond the current bar): max
  **500** bars into the future.
- **Backtest orders**: 9,000 normal (older orders trimmed once exceeded, no longer a
  hard error as of v6), or 1,000,000 with Deep Backtesting enabled.

## 7. Strategy-specific notes

- `strategy.entry()` handles reversing/pyramiding bookkeeping automatically —
  prefer it over `strategy.order()` unless raw order control is specifically needed.
- The `when=` parameter is gone (see table above) — gate order calls with `if`.
- Default margin percentage is now 100 (v6) — strategies won't open positions
  that exceed available capital and will margin-call short positions that lose too
  much, matching realistic trading more closely than v5's unlimited-margin default.
  If porting an old v5 strategy that assumed unlimited margin, set
  `margin_long=0, margin_short=0` explicitly to reproduce the old behavior — but
  be aware that's the *less* realistic setting.
- `strategy.exit()` parameter-pair evaluation changed (see table above) — re-test
  exits after porting from v5 if a call sets both a relative and absolute level for
  the same exit type.
- The old 9,000-order hard error is gone; excess orders are trimmed from history
  instead. Use `strategy.closedtrades.first_index` to find the oldest non-trimmed
  trade if you need to know where the trimming boundary is.
- If the user plans to publish the strategy or use it with an alert-driven bot,
  wire up `alert_message=` on `strategy.entry()`/`strategy.exit()` with a JSON
  payload — see `assets/templates/strategy_template.pine`.

## 8. Things v6 relaxed (used to error, now doesn't)

- `array.get()`, `array.set()`, `array.insert()`, `array.remove()` now accept
  **negative indices** (`-1` = last element), which raised a runtime error in v5.
  Still bounded by array size in both directions.
- The old hard cap of 550 total scopes (global + all local scopes from functions,
  loops, conditionals, UDTs, enums) is **removed entirely** — scripts can have an
  indefinite number of local scopes now. (The 500ms-per-loop and total execution
  time limits still apply, so this isn't a free pass on runaway loops.)
