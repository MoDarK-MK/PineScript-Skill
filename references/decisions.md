# Decision Record

Why things are the way they are. Short entries, one decision each, newest last.

This file exists because of a specific failure. `max_bars_back` was removed from
`reversal_pro` on the reasoning that a bounded scan made it unnecessary. That
reasoning was wrong — Pine cannot infer buffer depth from a dynamic index no
matter how tightly the loop is bounded — and it had to be reverted. The
information needed to avoid that was known and simply not written down anywhere
a future reader would look.

A decision with its reasoning recorded can be revisited. A decision without one
gets re-litigated, or quietly reversed by someone who was not there.

Format: **what was decided**, *why*, and what would **change our mind**.

---

## D1 — `max_bars_back = 1000` stays, on every script with a dynamic history index

**Decided:** any script indexing history with a loop variable (`high[i]`)
declares `max_bars_back`.

**Why:** Pine determines the history buffer statically. A dynamic index is
opaque to that analysis, so the buffer must be requested explicitly. Bounding
the loop does not help — the compiler cannot see the bound.

**Would change our mind:** nothing available. This is a platform property, not a
preference. It was tried the other way and produced a runtime error.

---

## D2 — Buy/sell volume is estimated from close-position-in-range

**Decided:** `buyShare = (close - low) / (high - low)`, applied to each bar's
volume, with a doji contributing 50/50 rather than being dropped.

**Why:** Pine exposes no bid/ask, so no script can know the aggressor. This is
the standard approximation for a profile of this kind, it is cheap, and it works
on every plan.

**Known cost, stated in every file that uses it:** it is wrong on bars that
reverse hard intrabar — exactly where you would most want it to be right. It is
not order flow and no file here claims it is.

**Would change our mind:** TradingView exposing aggressor data. Nothing else.

---

## D3 — `swing_volume_profile` does not use `request.security_lower_tf()`

**Decided:** the per-swing profile splits volume with D2 rather than reading
intrabar data.

**Why:** the target chart is 5-minute. The finest intrabar resolution available
without a Premium plan is 1 minute — **five sub-bars per candle**. That is
barely better than the range split and far more expensive, and seconds
resolutions fail the entire script on a non-Premium plan (PINE044).

**Would change our mind:** a higher target timeframe, where a 1-minute request
buys 15 or 60 sub-bars instead of 5. `indicators/volume_pro` is where intrabar
genuinely pays off, and that is why the two scripts differ.

---

## D4 — Delta is shown as bar colouring, not as a CVD pane

**Decided:** `volume_pro` tints candles by whether buying or selling dominated,
and leaves CVD in the data window.

**Why:** a real CVD pane needs `overlay = false`. The footprint needs
`overlay = true`. One script cannot have both, and the footprint is the reason
the script exists.

**Would change our mind:** shipping a second, separate pane indicator. That is a
different script, not a setting.

---

## D5 — The shared scoring engine is duplicated, and held identical by a test

**Decided:** `reversal_pro` and `reversal_pro_strategy` each contain a full copy
of the scoring engine, delimited by `SHARED SCORING ENGINE BEGIN/END` markers
and compared byte-for-byte by `tests/test_shared_engine.py`.

**Why:** Pine has no local file imports. The alternatives were a published
library (a real dependency with its own versioning and publication step) or a
comment asking future readers to keep two copies in sync. A comment is not a
mechanism; a failing test is.

**Would change our mind:** nothing currently available. D9 moved the *pure*
helpers into a library, but the scoring engine reads series data and inputs, so
it cannot follow them. The byte-identical test is not a holding pattern here —
it is the answer, given what Pine allows.

---

## D6 — Alerts are gated on `barstate.isconfirmed` by default

**Decided:** signal alerts fire on bar close unless the user opts out.

**Why:** a pivot can form mid-bar and vanish before the bar closes. An alert
that says "confirmed" must not fire on one that was not. The opposite default
produces more alerts and less trust.

**Would change our mind:** nothing. It is an input, so anyone who wants the
other behaviour has it.

---

## D7 — Drawings live in `var` pools and are repositioned, never recreated

**Decided:** create once, update with `.set_*()`, hide the unused tail.

**Why:** deleting and recreating drawings every tick churns object IDs, flickers
visibly on a live chart, and burns the 500-object budget. Repositioning does
none of that.

**Cost, accepted:** pool code is longer and less obvious than `label.new()` in a
loop, which is why `references/snippets/` carries the pattern.

---

## D8 — The row budget is spent, not divided

**Decided:** profile rows are **built** at the resolution requested; only the
**drawing** is rationed, empty rows cost no box, and the newest swing draws
first.

**Why:** building rows costs arrays; drawing them costs boxes. Only drawing is
capped at 500 by TradingView, and the marker lines — POC, Max Buy, Max Sell —
come from the build, not the draw. Dividing a fixed budget across swings capped
resolution for a reason that did not apply to the thing users actually care
about.

**Would change our mind:** nothing known. The earlier model was simply
conflating two different resources.

---

## D9 — The pure helpers move to a library; the stateful ones do not

**Decided:** `libraries/pine_toolkit` exports the palette, the formatters, the
maths helpers and the constant mappers. Drawing pools and the reversal scoring
engine stay duplicated.

**Why the split, and not "move everything":** Pine restricts what a library may
contain, and a pure function is the part that is unambiguously allowed. It is
also the part that is safe to share — a stateful helper imported into four
scripts is a shared mutable dependency, which is a worse problem than the
duplication it would replace. Pools hold `var` state; the scoring engine reads
series data and inputs. Both stay where they are, and D5's byte-identical test
still holds the engine's two copies together.

**Not yet compile-verified.** Libraries have publication requirements no offline
tool can check. The library must be pasted and published before any script here
imports it, and until then nothing depends on it.

**Would change our mind about the remainder:** nothing available. The boundary
is Pine's, not a preference.

---

## D10 — The linter will never claim to be a compiler

**Decided:** every entry point that reports a clean result says so alongside the
limitation, and `--fix` only repairs rules with exactly one correct rewrite.

**Why:** TradingView publishes no compiler CLI or API. A tool that implies
otherwise converts "your script has no known problems" into "your script
compiles", and the second is a promise this cannot keep. The compile-error
fixture corpus exists because the honest answer to a missed error is a new
rule, not a louder claim.

**Would change our mind:** TradingView publishing a compiler API.
