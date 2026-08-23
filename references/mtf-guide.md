# Multi-Timeframe Guide (`request.*`)

The largest gap in these references, and the source of the most common class of
real Pine bug: a script that backtests beautifully and behaves differently live,
because it was reading data that did not exist yet.

Nothing here is about style. Every item is a behaviour difference you can
observe.

---

## 1. The one thing to understand first

A higher-timeframe bar is **open** for many chart bars. On a 5-minute chart, the
daily bar is open for 288 of them. So "the daily close" has two possible
meanings at any moment:

- the close of the **last daily bar that finished** — stable, knowable, safe
- the current value of the **daily bar still forming** — changes on every tick,
  and on a historical bar it is a value nobody could have known at that time

Almost every repainting complaint reduces to a script silently taking the second
meaning while the author assumed the first.

---

## 2. The three combinations, and what each actually gives you

```pinescript
// A — live, honest, repaints intrabar
float dHigh = request.security(syminfo.tickerid, "D", high)

// B — stable and historically accurate (the default recommendation)
float dHigh = request.security(syminfo.tickerid, "D", high[1],
     lookahead = barmerge.lookahead_on)

// C — THE BUG
float dHigh = request.security(syminfo.tickerid, "D", high,
     lookahead = barmerge.lookahead_on)
```

**A** (`lookahead_off`, no offset) returns the forming HTF bar's running value.
It repaints within the HTF bar — which is correct behaviour for something meant
to show a live level, and wrong for anything a signal depends on. Backtest
results from it are optimistic in a way that does not show up as an error.

**B** offsets the expression by one HTF bar, so it reads only the last CLOSED
HTF bar, then uses `lookahead_on` to align that closed value to the correct
chart bars. The offset is what makes the lookahead safe. This pair is the
standard non-repainting idiom, and it is what the reversal indicator here uses for its
previous-day/week/month levels.

**C** is the actual mistake. `lookahead_on` without the offset lets historical
bars see the HTF bar's final value before that bar closed. It is invisible on
the chart, produces a backtest that cannot be reproduced live, and is the single
most common way a strategy lies to its author.

> Rule of thumb: `lookahead = barmerge.lookahead_on` and `[1]` travel together.
> Seeing one without the other is worth a second look every time. PINE006 flags
> a `request.security()` with no explicit `lookahead=` for the same reason —
> not because the default is wrong, but because the choice should be visible.

---

## 3. Never request a LOWER timeframe with `request.security()`

`request.security()` is defined for a timeframe higher than or equal to the
chart's. Asking it for a lower one does not error — it returns something, and
what it returns is not what you want.

For intrabar data use `request.security_lower_tf()`, which returns an **array**
of every lower-timeframe value inside the current chart bar:

```pinescript
array<float> intrabarVolumes = request.security_lower_tf(syminfo.tickerid, "1", volume)
```

Three things that bite:

- The array can be **empty** on the first bars, or when the lower timeframe has
  no data. Guard with `array.size() > 0`, never assume.
- The number of sub-bars is capped, and TradingView limits how far back
  intrabar data is available — deep history usually returns nothing.
- Seconds-based resolutions (`"1S"`, `"5S"`) require a **Premium** plan, and on
  a lower plan the request fails the ENTIRE script, not just that call. See
  PINE044 for the input-gated fallback pattern.

Weigh the cost honestly before reaching for it. On a 5-minute chart the finest
non-Premium resolution is 1 minute — five sub-bars per candle. That is still a
real improvement over modelling the spread from one bar, and it compounds
through everything built on those rows, but it is five times the work and the
intrabar budget runs out on older history. Build the fallback first, then add
the request.

---

## 4. Gaps

```pinescript
request.security(sym, tf, expr, gaps = barmerge.gaps_off)   // default
request.security(sym, tf, expr, gaps = barmerge.gaps_on)
```

`gaps_off` repeats the last known HTF value on every chart bar — a continuous
series, which is what you want for a level, a moving average, or anything you
plot. `gaps_on` returns `na` on every chart bar except the one where the HTF bar
closes — which is what you want when you need to detect *the moment* new HTF
data arrived, and nothing else.

Using `gaps_on` and then `nz()`-ing the result is a sign the answer was
`gaps_off` all along.

---

## 5. The call budget is real, and smaller than it looks

TradingView allows **40 unique `request.*()` calls** per script. Unique is the
operative word: identical symbol + timeframe + expression + parameters is one
call, and the same tuple written twice costs one, not two.

The lever that matters: **one call can return a tuple.**

```pinescript
// Three calls against the budget:
float dOpen  = request.security(syminfo.tickerid, "D", open[1],  lookahead = barmerge.lookahead_on)
float dHigh  = request.security(syminfo.tickerid, "D", high[1],  lookahead = barmerge.lookahead_on)
float dClose = request.security(syminfo.tickerid, "D", close[1], lookahead = barmerge.lookahead_on)

// One:
[dOpen, dHigh, dClose] = request.security(
     syminfo.tickerid, "D", [open[1], high[1], close[1]],
     lookahead = barmerge.lookahead_on)
```

That is not a micro-optimisation. Each `request.*()` is a separate data
evaluation, and it is the most expensive thing most indicators do. PINE039
flags duplicate calls and PINE048 warns as the count approaches 40.

---

## 6. Comparing timeframes

String comparison against `timeframe.period` is a trap: `"60"`, `"1H"` and
`"H"` can all mean the same thing depending on where the string came from, and
`timeframe.period == "1"` is true only for exactly one spelling.

```pinescript
// fragile
bool isIntraday = timeframe.period == "5" or timeframe.period == "15"

// robust
bool isIntraday = timeframe.in_seconds() < timeframe.in_seconds("60")
```

`timeframe.in_seconds()` normalises everything to a number. PINE016 flags the
fragile form when a unit string is compared with no multiplier.

---

## 7. What repaints, and what "repaint" even means

The word covers three different things, and separating them is most of the
argument:

| Kind | Happens when | Is it a bug? |
|---|---|---|
| **HTF repaint** | A forming HTF bar's value changes intrabar | Only if a signal depends on it |
| **Historical/realtime mismatch** | Historical bars are calculated once; realtime bars recalculate on every tick | No — it is how Pine works |
| **Lookahead** | Historical bars use data from the future | **Always** |

The first is a design choice. The second is unavoidable and the reason
`barstate.isconfirmed` exists. The third is the only one that is unambiguously
wrong, and combination **C** above is how it usually gets in.

A live price readout SHOULD repaint — that is what "live" means. A signal that
claims to be confirmed should not. The reversal indicator here gates its alerts on
`barstate.isconfirmed` by default for exactly this reason: a pivot can form
mid-bar and vanish before the bar closes, and an alert saying "confirmed" must
not fire on one that was not.

---

## 8. Checklist before shipping anything multi-timeframe

- [ ] Every `request.security()` has an explicit `lookahead=` (PINE006)
- [ ] Every `lookahead_on` has a matching `[1]` on its expression
- [ ] No `request.security()` asks for a timeframe below the chart's
- [ ] `request.security_lower_tf()` results are guarded with `array.size() > 0`
- [ ] Seconds resolutions are behind an input defaulting to OFF (PINE044)
- [ ] Calls that share symbol/timeframe/parameters are merged into one tuple
- [ ] Signals and alerts are gated on `barstate.isconfirmed`
- [ ] The script has been watched live for at least one HTF bar close

The last one is not optional. Nothing in this file substitutes for it.
