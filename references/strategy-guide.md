# Strategy Building Guide

The engineering side of writing a Pine strategy: signal design, sizing math, the
four risk modules, filters, and the ways a backtest lies to you.

Three docs divide this territory and none of them repeat each other:

| Doc | Owns |
|---|---|
| `references/publishing-guide.md` | TradingView **policy** — what you must do to publish a strategy |
| `references/pine-v6-guide.md` §7 | Pine v6 **language semantics** for `strategy.*` |
| **this file** | **Engineering** — how to actually build one that isn't fooling you |

The reference implementation of everything here is
`strategies/reversal_pro_strategy/src/reversal_pro_strategy.pine`, and
`assets/templates/strategy_template.pine` is the same machinery with a
placeholder signal.

---

## 1. What a strategy is, and what a backtest is not

An indicator says *"here is a thing"*. A strategy says *"here is a thing, and I
took this much risk on it, and here is what happened"*. The second claim is much
larger, and almost all of the difficulty is in the parts that aren't the signal.

A backtest is **not** a forecast. At best it is a lower bound on how wrong you
can be: if the idea fails on the data you already have, it will fail on data you
don't. The reverse doesn't hold. You already know this chart went up — you chose
the symbol *after* seeing its history, and that alone is enough to produce a
profitable-looking backtest from a coin flip.

Two engine settings change what "the backtest" even means:

- **`process_orders_on_close=true`** fills at the signal bar's **close**. This is
  right for signals computed from a closed bar, and optimistic if your idea needs
  an intrabar fill. The default (`false`) fills at the **next bar's open**, which
  is more conservative and often more realistic for discretionary-style entries.
- **`calc_on_every_tick=true`** makes the script recalculate intrabar in
  realtime, so historical and realtime results diverge — the historical run only
  ever sees closed bars. Leave it off for anything you intend to publish.

## 2. Signal design: entry, exit, and the seam between them

A complete trade specification is three things, and only the first is "the
signal":

1. **Entry** — the condition that puts you in.
2. **Invalidation** — the price that proves the idea wrong (your stop). This is
   what makes risk measurable, and therefore what makes position sizing possible.
3. **Objective** — where the idea has paid off (your target, or a trailing rule).

**An exit rule is not the mirror of the entry rule.** "Buy the cross up, sell the
cross down" is one rule pretending to be two: it has no invalidation, so every
trade risks an unbounded amount and the concept of "risk 1% per trade" is
meaningless. If you take one thing from this document, take this one.

### Confirmation vs repainting

A signal computed from the *current, unclosed* bar can change before that bar
closes. Gate anything meant to be final with `barstate.isconfirmed`, or reference
`[1]`.

Pivots are the interesting case. `ta.pivothigh(high, len, len)` returns `na`
until `len` bars **after** the pivot bar. An indicator draws the label back at
`bar_index[len]`, which looks like it predicted the turn. A strategy **must not**
do that — it enters at the confirmation bar's close, where the signal actually
exists. That makes pivot strategies non-repainting by construction, but it also
means your entry is `len` bars and a meaningful distance away from the extreme,
which is exactly why the stop is measured from the *entry*, not from the pivot.

## 3. Position sizing math

The whole point of a stop is that it converts an idea into a number you can size
against:

```
riskCapital  = equity × riskPercent / 100          // account currency
perUnitRisk  = stopDistance × syminfo.pointvalue   // account currency per contract
qty          = riskCapital / perUnitRisk
```

Four things that go wrong here, all of them silent:

- **`syminfo.pointvalue` omitted.** It converts a 1.0 price move on one contract
  into account currency: 1 for stocks and crypto, **50 for ES**, 20 for NQ. Since
  it's 1 on the instruments most people test on, leaving it out looks fine until
  someone runs your strategy on futures with a 50× position.
- **Rounding to zero.** `math.floor(qty / step) * step` can produce `0`. The
  entry then silently doesn't happen, and your backtest is quietly biased toward
  whichever regime happened to size above one lot. Always gate on `qty > 0`.
- **No leverage cap.** A very tight stop implies enormous notional. With
  `margin_long=100` the engine rejects the order outright and you lose the trade
  with no error in the log. Cap notional separately from risk:
  `qty = math.min(riskQty, equity × maxNotionalPct / 100 / (price × pointvalue))`.
- **Currency mismatch.** If `syminfo.currency` differs from the account currency,
  `riskCapital` and `perUnitRisk` are in different units and the sizing is wrong
  by the FX rate. Convert with `request.currency_rate()`.

Sizing off `strategy.equity` compounds (it includes open P&L); sizing off
`strategy.initial_capital + strategy.netprofit` uses closed equity and is more
conservative. Both are defensible — pick one deliberately.

## 4. The four risk modules

Each one fixes something and costs something. A module you can't state the cost
of is a module you added because it felt professional.

### 4.1 Risk-based + ATR sizing

**Fixes:** every trade risks the same fraction of the account regardless of
volatility, so one wild bar can't do ten trades' worth of damage.
**Costs:** in high volatility your size shrinks, so a correct call in a violent
market pays less than the same call in a calm one.

An ATR stop adapts to the instrument and regime; a percent stop doesn't but is
predictable. Floor the stop at a minimum tick count either way — a tight-range
bar can otherwise produce a near-zero stop, which divides by zero in the sizing
math and asks for an unbounded position.

### 4.2 Breakeven

**Fixes:** removes the "gave back a winner" trade from your distribution.
**Costs:** cuts winners. A stop parked at entry gets hit by ordinary noise on the
way to the target, converting would-be winners into scratches. Breakeven is a
psychological instrument as much as a statistical one — measure whether it helps
before assuming it does.

**Move it past entry, not to entry.** `strategy.position_avg_price` excludes
commission, so a literal-breakeven stop still books a round-trip-cost loss. The
template offsets by 0.1R by default for exactly this reason.

### 4.3 Trailing

**Fixes:** lets a trend run past any fixed target.
**Costs:** in chop it converts a trend-following edge into a tax — you get
stopped out near the top of every small swing.

A Pine-computed trailing stop only moves on **bar close**. A broker-side trailing
stop (`trail_price`/`trail_offset`) moves intrabar, which is more realistic but
gives you two independent trigger mechanisms if you also use `stop=`, and in v6
whichever triggers first wins. See §9.

### 4.4 Partial exits (TP1/TP2)

**Fixes:** takes money off the table, reduces variance, makes the runner free.
**Costs:** **caps your right tail.** Trend-following edges live entirely in the
top few percent of trades; taking half off at 1R systematically removes exactly
the part of the distribution that pays for everything else. You cannot both take
partials and complain that your average R is small — those are the same fact.

Two mechanical traps:

- `qty_percent=50` of a 1-contract position is 0.5. On whole-lot instruments the
  partial either rounds away or closes the entire position. Guard with a
  "position is at least 2 lots" check.
- **Each partial records its own closed trade.** `strategy.closedtrades` roughly
  doubles, win rate inflates (TP1 almost always registers as a winner), and the
  100-trade publishing threshold is trivially "met" by a strategy that took 50
  positions. Count positions separately — see §6.

## 5. Filters

Direction, trend regime, volatility regime, session, and date window are all the
same kind of thing: they answer *"should I be looking for a trade right now?"*

**Filter entries, never filter exits.** A position opened inside a window and
then abandoned when the window closes is stranded there forever. Every filter
gates the entry; the flush runs unconditionally:

```pinescript
if useDateWindowInput and not inWindow and strategy.position_size != 0
    strategy.close_all(comment="Window end")
```

Two Pine specifics:

- `time(timeframe.period, session, tz)` returns **`na`** outside the session, not
  `0` or `false`. Test with `not na(...)`.
- `time` is the bar's **open** time, so a date bound compares against the bar that
  *starts* before the cut-off.

Every filter you add is also a parameter you can tune — see §7.

## 6. Backtest realism in code

> The **policy** this satisfies is in `references/publishing-guide.md` §
> "Strategy-specific realism requirements". This section only covers how to
> satisfy it in code.

| Policy line | What implements it |
|---|---|
| Realistic starting capital | `initial_capital=10000` in the declaration |
| Realistic costs | `commission_type` + `commission_value` + `slippage` |
| No unlimited leverage | `margin_long=100, margin_short=100` (the v6 default) |
| Risk ≤ ~10% of equity per trade | `riskPercentInput` with `maxval=10.0` — a UI-level cap is stronger than a lint warning |
| 100+ trades | count **positions**, not `strategy.closedtrades` |

That last row is the one people get wrong. With partials on,
`strategy.closedtrades` counts exit records, not positions. Track entries
yourself:

```pinescript
var int entryCount = 0
bool justFilled = strategy.position_size != 0 and strategy.position_size[1] == 0
if justFilled
    entryCount += 1
```

and report both numbers on the dashboard so the distinction is visible rather
than buried. Note also that v6 **trims** old orders on very long histories rather
than erroring, so `strategy.closedtrades` can under-report —
`strategy.closedtrades.first_index` tells you where the trimming boundary is.

`scripts/generate_release_bundle.py` now checks the mechanical subset of this
automatically for projects with `"kind": "strategy"` (lookahead bias,
non-standard chart types, zero-cost backtests, sizing sanity) and pre-fills the
publish description's disclosure section from your actual declaration values.
Trade count, Strategy Tester warnings, and the chart you publish on remain
manual.

## 7. Overfitting traps

Every input is a knob, and every knob is a chance to fit noise. Rough heuristic:
**you need far more trades than parameters — hundreds, not tens.** A strategy
with 8 tunable inputs and 40 trades has learned the specific wiggles of one
price series and nothing else.

Specific tells, in rough order of how often they show up:

- **"I tuned it until the equity curve was smooth."** Smoothness is the thing
  overfitting produces. A real edge has ugly drawdowns.
- **Per-symbol parameter values.** If `atrStopMultInput` has to be 1.7 on this
  symbol and 3.2 on that one, you have two curve fits, not one strategy.
- **A date range that starts suspiciously late.** Check whether the strategy
  survives the period you excluded.
- **Filters added until the losers disappeared.** Each filter removed specific
  historical trades; that is not the same as it removing future ones.
- **Reoptimising after every drawdown.** This is fitting to the most recent
  noise, continuously.

A cheap robustness check, and the one worth doing first: move each parameter
±25% and see whether the result degrades gracefully or falls off a cliff. An edge
that only exists at exactly `atrStopMult=2.0` doesn't exist.

## 8. Walk-forward thinking

The date-window inputs exist for this, which is why they're inputs and not
constants.

The minimum honest version: split your history in two, develop on the first half
only, then run the second half **once** with everything frozen. The moment you
adjust anything after seeing out-of-sample results, that data is in-sample and
you need new data.

Rolling walk-forward is the same idea repeated: optimise on window N, test on
window N+1, step forward, and judge the strategy by the concatenated
out-of-sample results only. TradingView has no automation for this, so it's
manual — set the window, record the result, step. Record what you find in the
project's `CHANGELOG.md` or a `notes.md` beside it, because unrecorded results
become "I think it was fine" within a week.

## 9. Pine v6 strategy pitfalls

Language semantics live in `references/pine-v6-guide.md` §7; this table is the
strategy-writing shortlist, with the lint rule that catches each one.

| Pitfall | Consequence | Caught by |
|---|---|---|
| `strategy.exit()` with no level argument | Places no order — the position has no stop at all | **PINE029** |
| Relative + absolute level of the same type | v5 used absolute; v6 uses whichever triggers **first** | **PINE030** |
| `loss`/`profit`/`trail_points`/`trail_offset` given a price | Off by `1/syminfo.mintick` | **PINE031** |
| `strategy.position_avg_price` used while flat | It's `na`, so the stop is `na` and the exit does nothing | **PINE032** |
| `qty_percent` outside 0-100, `qty` ≤ 0 | Order rejected or closes nothing | **PINE033** |
| `from_entry` naming a nonexistent id | Exit attaches to nothing and never fires | **PINE034** |
| Entries with no exit mechanism | No trade has defined risk | **PINE035** |
| `when=` on an order call | Removed in v6 | **PINE010** |
| `pyramiding=input.int(...)` | Compile error — it's `const int` | — |
| Resetting state on `position_size == 0` | Also fires on the signal bar (order hasn't filled), wiping the plan | — |
| `ta.*()` after an `and`/`or` | Lazy evaluation may skip it, corrupting its state | **PINE017** |

Two that no linter can catch, and that decide whether the risk code is correct:

**Same `id` updates, different `id` creates.** Calling `strategy.exit("L Runner",
...)` every bar *modifies* the live order — that is precisely the mechanism that
makes a computed trailing stop move. A bar-varying id would stack duplicate
orders instead.

**Fill timing vs `position_size`.** With `process_orders_on_close=true`, the entry
fills at the signal bar's close, so `strategy.position_size` is still `0` on the
bar you place the order. Any "reset the plan when flat" block written as
`if strategy.position_size == 0` will wipe the plan you just armed. Reset on the
transition instead:

```pinescript
if strategy.position_size == 0 and strategy.position_size[1] != 0
    // we JUST went flat — safe to clear
```

## 10. Reference implementation

`strategies/reversal_pro_strategy/` turns the Reversal Pro indicator's 0-5 pivot
scoring engine into a full strategy: entries at the pivot **confirmation** bar,
risk-based sizing off an ATR stop, breakeven + trailing resolved into one
ratcheting stop, TP1/TP2 partials, and every filter in §5.

Read it alongside `indicators/reversal_pro/` to see the same engine used both
ways — the indicator draws the pivot back where it happened, the strategy trades
it where it was confirmed. That difference is §2 in one screenshot.
