# Troubleshooting

Symptom first, because that is what you have when something is wrong.

**Every row in this file happened.** Not a hypothetical catalogue — each one was
hit in this repo, usually by pasting a script into TradingView and watching it
do the wrong thing. Where a lint rule was added afterwards so it could not
happen again, the rule is named.

---

## Nothing draws

| Symptom | Likely cause | Check |
|---|---|---|
| A whole feature is silently absent, no error | A `var x = na` guard compared with `!=` — Pine does not compare reliably against `na`, so the guard never matched and the code never ran | **PINE045**. Use `na(x)` |
| Drawings appear, then older ones vanish as you scroll | The `max_*_count` default of 50 | **PINE052**. Set `max_boxes_count` / `max_lines_count` / `max_labels_count` (max 500) |
| Nothing draws on the last bar only | The drawing block is inside `if barstate.islast` but the data it needs is only built on confirmed bars | Build on confirm, draw on last — they are different guards |
| A loop over N items draws nothing when N is 0 | Pine counts **DOWN** when a `for` loop's end value is below its start, so `for i = 0 to n - 1` with `n = 0` runs with `i = 0` and `i = -1` | Guard with `if n > 0` before the loop |
| Boxes render but with zero height | Row height computed from a range that collapsed to zero | Floor the span at `syminfo.mintick`, never at `mintick * rows` — see below |

### The `mintick * rows` trap

Flooring a profile's price span at `syminfo.mintick * rows` looks like it
guarantees a usable row height. What it actually does is **inflate the range**
of any swing narrower than the row count, drawing a profile taller than the
thing it describes. Invisible at 30 rows, badly wrong at 500. Floor at one tick
and reduce the row count to the tick span instead.

---

## It compiles, then errors at runtime

| Symptom | Cause | Fix |
|---|---|---|
| `Pine cannot determine the referencing length of a series` | History accessed with a **loop variable** (`high[i]`), which Pine cannot analyse statically | Add `max_bars_back = 1000` to the declaration. A tightly bounded loop does **not** remove this requirement — that mistake was made here once and had to be reverted |
| `Loop takes too long to execute` | A loop nest whose worst case explodes when an input is turned up | **PINE053**. Cost the nest at its `maxval`s, not at its defaults |
| Script times out (20 s) | Whole-history recalculation on every realtime tick | Memoise: fingerprint the inputs, recompute only when they change. See `performance-guide.md` |
| An input used as a history offset errors on large values | No `maxval`, so the offset can reach past the history buffer | Give every history-offset input a `maxval` |

---

## Compile errors

| TradingView says | Rule | Meaning |
|---|---|---|
| `Cannot modify global variable "x" in function` (CE10088) | **PINE042** | A function assigned to a global. Return the value and assign at the call site |
| `Return type of one of the "if" or "switch" blocks is not compatible` (CE10235) | **PINE043** | A function's **trailing** if/else has branches of different types. End the function on one plain expression |
| `Cannot use 'input' in local scope` | **PINE046** | `input.*()` inside a function/if/loop |
| `Cannot use 'plot' in local scope` | **PINE047** | Same, for the plot family |
| `Cannot use 'strategy.entry' in local scope` | **PINE049** | An order call inside a function |
| `Undeclared identifier 'x'` | **PINE050** | `x := ...` where x was never declared. Usually a typo in the target name |
| `The 'request' calls limit was exceeded` | **PINE048** | Over 40 unique `request.*()`. Merge calls into tuples — see `mtf-guide.md` §5 |
| `This script uses seconds-based timeframes, which are only available to users with Premium…` | **PINE044** | A seconds resolution reached a non-Premium plan, and it fails the WHOLE script, not that one call |

---

## It looks wrong

| Symptom | Cause |
|---|---|
| Table cells are invisible / black on black | Pine defaults `table.cell` text to **black**. **PINE036** — every cell needs an explicit `text_color=` |
| Numbers jitter left and right as price ticks | Values are left-aligned. Right-align the value column so digits line up |
| Two labels sit on top of each other | Levels clustered. Nudge the labels apart; leave the lines at their true prices |
| Chart text looks oversized next to TradingView's own | `size.large` / `size.huge`. **PINE041** — the design system caps at `size.normal` |
| A dashboard sits on top of another script's | Both defaulted to the same corner. Make the position an input |
| The profile buries the candles | The longest row spans the whole swing. Cap it at a percentage of the swing width |

---

## It behaves differently live than in the backtest

Start with `mtf-guide.md` §2 and §7 — this is almost always one of three things:

1. **Lookahead**: `lookahead = barmerge.lookahead_on` without a `[1]` offset.
2. **Signals taken at the pivot bar** rather than at its confirmation bar. A
   pivot with length N is only known N bars later. Entering at the pivot bar is
   lookahead wearing a different hat.
3. **Alerts not gated on `barstate.isconfirmed`**. A signal can form mid-bar and
   disappear before the bar closes.

---

## The tick arrow points the wrong way

Comparing `close` to `close[1]` gives **bar** direction, not **tick** direction.
Only `varip` survives between intrabar ticks:

```pinescript
varip float prevTickClose = na
varip bool  tickWasUp     = true
if barstate.isrealtime
    if not na(prevTickClose) and close != prevTickClose
        tickWasUp := close > prevTickClose
    prevTickClose := close
```

This is the rare case where `varip` is correct. See `performance-guide.md` for
why it is wrong nearly everywhere else.

---

## Buy/sell volume looks wrong on reversal candles

It is wrong, and it cannot be otherwise. Pine exposes **no bid/ask**, so no
script can know which side was the aggressor. The estimate used here splits each
bar's volume by where it closed inside its own range:

```
buyShare = (close - low) / (high - low)
```

That is right most of the time and wrong on bars that reverse hard intrabar —
which is exactly where you would most want it to be right. Intrabar data
(`request.security_lower_tf`) narrows the error without eliminating it, at real
cost and with a Premium requirement for seconds resolutions.

Any script claiming true order flow from standard TradingView data is claiming
something the platform does not provide.

---

## The linter says it is clean and TradingView disagrees

That is expected, and it is the honest limit of this tool. **The linter is not a
compiler.** TradingView publishes no compiler CLI or API, so nothing offline can
guarantee a script compiles.

What to do with such a case, in order:

1. Fix the script.
2. Add a fixture to `tests/fixtures/compile_errors/` that reproduces it.
3. Add the rule that catches it, with `scripts/new_rule.py`.
4. Add the row to the error table in `lint-rules.md`.

Step 2 is the one people skip, and it is the one that makes the difference
between fixing a bug and fixing a class of bugs.
