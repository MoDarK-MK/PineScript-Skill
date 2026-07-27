# Changelog

## [Unreleased]
- (nothing yet)

## [1.1.1] - 2026-07-27
- Fix CE10088/CE10235 in the test block

## [1.1.0] - 2026-07-27
### Added
- Order Blocks module: registers the origin candle of each displacement move that breaks the last confirmed swing, drawn as a zone that fades (or hides) once price trades back into it
- Each block carries a volume bar whose WIDTH encodes that candle's volume relative to the heaviest live block, so the set reads like a volume histogram lying on its side
- Block labels show the volume compactly (1.24M) with a tooltip giving the zone range, origin-candle volume, and mitigation state
- Two alerts: new bullish / new bearish order block, sharing the existing bar-confirmation gate
- Fully customizable: max blocks per side, origin scan depth, minimum displacement in ATR, body vs full-wick zone, mitigation rule (wick touch vs body close through), fade vs hide, transparency, and both colors

### Fixed
- Restored `max_bars_back=1000`. Removing it in 1.0.0 was wrong: the volume-profile scan indexes history with a loop variable, and Pine cannot infer the buffer depth from a dynamic index regardless of how tightly the loop is bounded. The order-block origin scan has the same requirement.
- Order blocks with volume bars

## [1.0.0] - 2026-07-27
### Performance
- The volume-profile scan is now fingerprinted against the bar window it covers, so the ~900-iteration loop runs at most once per bar instead of on every realtime tick
- The profile buffer is a single `var` array cleared with `array.fill()` rather than a fresh allocation per tick
- Level and zone drawings are created once and repositioned with `.set_*()` instead of being deleted and rebuilt every tick — no churn, no flicker
- Merged two `request.security()` calls that shared symbol/timeframe/lookahead (the daily open now rides along with PDH/PDL/PDC), removing one higher-timeframe series evaluation
- Hoisted `sizeFrom`/`lineStyleFrom` out of the per-level loop; they switch over constant inputs
- Replaced `max_bars_back=1000` with a bounded scan, and gave every input used as a history offset a `maxval` so a large value can no longer produce a runtime error

### Correctness
- The tick-direction arrow now tracks actual ticks via `varip`; it previously compared against the previous BAR's close, which is bar direction, not tick direction
- Alerts are gated on `barstate.isconfirmed` by default (new input) — a pivot can form mid-bar and vanish, and an alert saying "confirmed" should not fire on one that was not
- The test block uses the assertion-counter pattern instead of one label per assertion per bar, so it can no longer exhaust the 500-label budget

### Visual
- Added a theme picker (Dark/Light) driving text, muted-label, and panel colors — previously only the table touched theme at all
- Table gained a merged title row, left-aligned labels and right-aligned values so digits stop jittering as price ticks, and a default transparency of 15 instead of 80
- Level labels are nudged apart when levels cluster, so PDH/Swing H and CDL/PDL no longer stack on top of each other; the lines stay at their true prices
- Replaced the Material-Design rainbow level palette with a coherent set, and dropped `size.large` in favour of the `size.normal` cap
- Live-update rework, unified visual system

## [0.9.0] - 2026-07-26
- Removed the SETUP trade-suggestion block from the table; the table now shows the live price and swing position only
- With nothing left consuming it, the multi-timeframe bias engine went too: reversalBias(), the five request.security() calls, and the Bias Timeframe inputs (5 fewer requests against TradingView's 40-call limit)
- Removed the Trade Suggestion input group (account size, risk %, size unit, ATR stop, target R, min confidence)
- Merged the two redundant table toggles into one, and dropped the write-only hvzVolume variable
- Remove the trade-suggestion block and the multi-timeframe bias engine

## [0.8.0] - 2026-07-26
- Removed the per-timeframe UP/DOWN rows from the table; it now shows the live price/swing header and the trade suggestion only
- The Bias Timeframe inputs are kept and still drive the 35% timeframe-consensus component of the suggestion's vote
- Dropped the now-unused biasRow() and tfLabel() helpers
- Remove per-timeframe rows from the table

## [0.7.0] - 2026-07-26
- Added a Trade Suggestion block to the table: BUY/SELL/WAIT with a confidence %, plus entry, stop, target, position size and risk amount
- Direction comes from a transparent weighted vote of the three signals the indicator already computes (pivot 45%, timeframe bias 35%, swing position 20%); the tooltip shows each vote
- Size is computed from your own Account Size and Risk % inputs, in units or forex lots (100k/10k/1k)
- Documented clearly that the suggestion is a mechanical readout, not advice, and that the size math ignores spread, commission, slippage and leverage
- Trade suggestion block with entry, stop, target and position size

## [0.6.0] - 2026-07-26
- Reversal labels now show the volume traded on the pivot bar, optionally as a multiple of the volume average
- Label tooltips gained a volume line (absolute and x-average)
- New High-Volume Zone module: builds a volume profile over the swing between the two most recent reversals and draws its Point of Control as a box, with an optional mid-line and label
- Documented that the zone approximates volume at each bar's hlc3 — Pine has no intrabar volume distribution
- Volume at reversals and high-volume zone between reversals

## [0.5.2] - 2026-07-25
- Default bias-table timeframes changed to 1m / 5m / 15m / 1H / 4H
- Default bias-table timeframes: 1m/5m/15m/1H/4H

## [0.5.1] - 2026-07-25
- Key-level labels now float just above their line (label.style_label_lower_left) instead of sitting on it, so the line no longer cuts through the text
- Float key-level labels above the line for readability

## [0.5.0] - 2026-07-25
- Added a LIVE header to the table: current price with an up/down tick arrow and the exact swing position (% of price between the last reversal low and high), recomputed every tick
- Expanded Key Levels: added previous-month high/low, live current-day high/low, and the most recent reversal swing high/low
- Level labels now show the live distance from price (percent or price, configurable) and the nearest level above/below is highlighted
- Whole dashboard and levels rebuild on every realtime tick, so everything tracks price live and to the tick
- Live price/swing tracker and expanded key levels with live distance

## [0.4.0] - 2026-07-25
- Added a per-timeframe Reversal-Bias table (UP%/DOWN% relative to each timeframe's nearest pivot, 5 configurable timeframes)
- Added a Key Levels module: previous day/week high-low-close and day open as fully customizable horizontal lines with labels
- Bias table and levels are fully customizable (position, size, colors, transparency, line style/width, which levels to show)
- Documented the bias number as a transparent heuristic blend, not a back-tested statistical probability
- Add per-timeframe bias table and customizable key levels

## [0.3.0] - 2026-07-22
- Upgraded the strength score from 0-3 to 0-5 stars
- Added two confirmations: wick rejection on the pivot candle, and major-swing extreme over a wider lookback
- New inputs: Wick Rejection ratio and Major Swing Lookback; 'Strong' threshold default raised to 4/5
- Max-strength (★★★★★) signals now render at large size with a width-3 line
- 5-star strength scoring (added wick-rejection and major-swing confirmations)

## [0.2.0] - 2026-07-19
- Extracted the reversal engine from the original multi-module indicator (RSI boxes, volume profile, trend table, and background removed)
- Signals now cover the whole chart history (old 300-bar window removed; capped only by TradingView's 500 label/line limit)
- Added a 0-3 strength score per pivot (RSI exhaustion + volume spike + candle confirmation) shown as stars on each label
- Added minimum-score display filter and STRONG bullish/bearish alert conditions
- Whole-chart reversal signals with 0-3 strength scoring

## [0.1.0] - 2026-07-19
### Added
- Initial version of Reversal Pro
