# Performance & Live-Update Guide

How to keep a Pine script fast and genuinely live at the same time. The hard
limits themselves are in `references/pine-v6-guide.md` §6 — this file is about
how to stay under them.

---

## 1. The budget you are spending

| Budget | Limit | What blows it |
|---|---|---|
| Total execution | **20 s** (Basic plan) / **40 s** (paid) | Work repeated across thousands of bars |
| Single loop | **500 ms per bar** | A long scan inside `barstate.islast`, re-run on every tick |
| Unique `request.*()` | **40** (64 Ultimate) | One call per timeframe per expression instead of tuples |
| Drawing IDs | **500** each for line/box/label | Objects created per bar and never deleted |
| Plot count | **64** | Each `plot`/`plotshape`/`bgcolor`/`fill`/`alertcondition` |

The one people miss: **`if barstate.islast` runs on every realtime tick, not once
per bar.** That is exactly what makes a dashboard feel live — and it is why a
900-iteration loop placed there can run several times a second on an active
symbol, against a 500 ms cap.

## 2. Tier your work

Decide, for each piece of work, which of these it belongs in. Most performance
problems are something sitting one tier too high.

| Tier | Runs | Put here |
|---|---|---|
| **Global** | every bar, plus every realtime tick | `ta.*` series that must see every bar to stay correct; `request.*()` |
| **Confirmed bar** (`barstate.isconfirmed`) | once per closed bar | Signals and alerts that must not fire on a bar that can still change |
| **Last bar** (`barstate.islast`) | every realtime tick | Cheap live readouts: price, distances, repositioning drawings |
| **On change** (fingerprint) | only when its inputs move | Scans, profiles, anything with a loop |

**`ta.*` must stay in the global tier.** Moving `ta.rsi()` inside a conditional
(or after an `and`, where v6's lazy evaluation may skip it) corrupts its internal
state, because it needs to see every bar. Compute it globally, use it anywhere.
The linter flags the `and`/`or` case as PINE017.

## 3. Recompute only when the inputs changed

The cheapest work is work you skip. Keep a fingerprint of whatever the result
genuinely depends on, and rebuild only when it moves:

```pinescript
var int   cachedLeft  = na
var int   cachedRight = na
var float cachedPoc   = na

if barstate.islast
    if cachedLeft != leftBar or cachedRight != rightBar
        cachedLeft  := leftBar
        cachedRight := rightBar
        cachedPoc   := expensiveScan(leftBar, rightBar)   // the loop lives here
    // Everything below still runs every tick — the drawing keeps tracking the
    // right edge live even though the scan didn't re-run.
    box.set_rightbottom(zoneBox, bar_index, cachedPoc)
```

This is the pattern that reconciles "must be live" with "must be fast": the
**display** updates every tick, the **computation** does not.

Pick the fingerprint from what the answer actually depends on. If a volume
profile covers bars `[leftBar, rightBar]`, those two integers *are* the
fingerprint — the bars between them are settled history and cannot change.

## 4. Reuse buffers instead of reallocating

```pinescript
// Bad: a fresh array allocated and discarded every tick.
if barstate.islast
    array<float> bins = array.new<float>(24, 0.0)

// Good: one buffer, cleared in place.
var array<float> bins = array.new<float>(24, 0.0)
if barstate.islast
    array.fill(bins, 0.0)
```

`array.new` inside a per-bar or per-tick block is flagged as **PINE037**. A
temporary inside a user function body is fine — that is an ordinary local.

## 5. Move drawings, don't rebuild them

Deleting and recreating N objects per tick costs N destructions plus N
allocations, and the drawings visibly flicker as they blink out and back.

```pinescript
// Bad: churn — flagged as PINE038.
if barstate.islast
    line.delete(myLine)
    myLine := line.new(x1, y, x2, y)

// Good: create once, then move.
var line myLine = na
if barstate.islast
    if na(myLine)
        myLine := line.new(x1, y, x2, y, xloc=xloc.bar_index)
    else
        line.set_xy1(myLine, x1, y)
        line.set_xy2(myLine, x2, y)
```

The setters exist for every drawing type: `line.set_xy1/set_xy2/set_color/
set_width/set_style/set_extend`, `box.set_lefttop/set_rightbottom/set_bgcolor`,
`label.set_xy/set_text/set_color/set_textcolor/set_size/set_tooltip`, and
`table.cell_set_text/cell_set_text_color/cell_set_bgcolor`.

**When the object count varies**, keep a `var array` pool: grow it when you need
more, reuse by index, and hide the surplus by setting it transparent. Because
the enabled-feature set is fixed for a whole run, the pool stabilises after the
first draw.

## 6. `request.security()` costs more than a slot

Each *unique* call instantiates and runs a separate higher-timeframe series.
Two calls that share symbol, timeframe and lookahead do that work twice for no
reason — return a tuple instead:

```pinescript
// Two HTF evaluations.
[pdh, pdl] = request.security(syminfo.tickerid, "D", [high[1], low[1]], lookahead=barmerge.lookahead_on)
float dayOpen = request.security(syminfo.tickerid, "D", open, lookahead=barmerge.lookahead_on)

// One.
[pdh, pdl, dayOpen] = request.security(
     syminfo.tickerid, "D", [high[1], low[1], open], lookahead=barmerge.lookahead_on)
```

Flagged as **PINE039**. Note that gating a `request.*()` behind a boolean input
does **not** save the evaluation — the series is instantiated regardless. Merge
calls; don't try to hide them behind a flag.

## 7. `max_bars_back` and unguarded inputs

A **dynamic index** — `high[i]` where `i` is a loop variable rather than a
constant — is what forces you to set a history buffer, because Pine can no
longer infer the depth it needs.

- `max_bars_back=1000` in the declaration applies that buffer to **every** series
  in the script, which costs memory on all of them.
- `max_bars_back(volume, 1000)` targets one series. Prefer it when only one or
  two series are indexed dynamically.
- Better still: bound the loop so the buffer is never needed. Clamping a scan to
  a range you already know is in-buffer removes the problem entirely.

**Give every input used as a history offset a `maxval`.** `input.int(15, "Pivot
Sensitivity", minval=2)` with no upper bound lets a user type 5000 and hit a
runtime "historical offset beyond max_bars_back" error that reads like a script
bug.

## 8. `var`, `varip`, and what rolls back

On a realtime bar Pine re-executes the script on every tick, and **restores every
`var` to its value at the last bar close first**. That rollback is load-bearing:

```pinescript
var float lastPivotHigh = na
if not na(ta.pivothigh(high, len, len))
    lastPivotHigh := pivotHigh
```

A pivot can appear mid-bar and vanish before that bar closes. Because
`lastPivotHigh` is `var`, the phantom is discarded on the next tick. Change it to
`varip` and the phantom **latches permanently**, silently corrupting everything
downstream. `varip` does not roll back — that is its entire purpose.

So use `varip` only when you genuinely need to remember something *between ticks
of the same bar*, and accept that it will not be undone. The canonical valid
case is tick direction, which is otherwise impossible to compute:

```pinescript
// close[1] is the previous BAR's close — this is bar direction, not tick direction.
bool wrong = close >= close[1]

varip float prevTickClose = na
varip bool  tickWasUp     = true
if barstate.isrealtime
    if not na(prevTickClose) and close != prevTickClose
        tickWasUp := close > prevTickClose
    prevTickClose := close
```

## 9. Alerts and unconfirmed bars

A condition computed on a forming bar can be true on one tick and false on the
next. An `alertcondition()` on such a series fires on the phantom. If the alert
message says "confirmed", gate it:

```pinescript
bool alertOk = not confirmedOnlyInput or barstate.isconfirmed
alertcondition(pivotFound and alertOk, "Pivot", "Pivot confirmed.")
```

Offer it as an input rather than hard-coding it — some users want the early,
repainting signal and understand the trade-off.

## 10. `calc_on_every_tick` (strategies)

Off by default, and worth leaving off for anything you publish: with it on, the
historical run (which only ever sees closed bars) and the realtime run diverge,
so the backtest stops describing what the strategy will do. It also multiplies
the strategy's execution cost by the tick rate. See
`references/strategy-guide.md` §1 for the backtest-realism side of this.

## 11. Test blocks are a budget item

One `label.new` per assertion per bar will exhaust the 500-label pool on any real
history, after which the oldest labels silently vanish and the chart lies to you.
Count instead, and draw only failures:

```pinescript
var int passCount = 0
var int failCount = 0

recordAssertion(bool condition, string description) =>
    if condition
        passCount += 1
    else
        failCount += 1
        label.new(bar_index, high, "FAIL: " + description, ...)
```

The full pattern is in `assets/templates/test_block_template.pine`.

## 12. Checklist

- Is any loop inside `barstate.islast` without a change fingerprint?
- Is any `array.new` inside a per-bar block missing `var`?
- Does any block delete and recreate drawings instead of moving them?
- Do two `request.security()` calls share symbol + timeframe + lookahead?
- Does every input used as a history offset have a `maxval`?
- Is any `varip` there for a reason other than intrabar memory?
- Do alerts that claim "confirmed" check `barstate.isconfirmed`?
- Does the test block count, or does it draw a label per assertion per bar?

PINE037–PINE039 catch four of these mechanically; the rest need a human.
