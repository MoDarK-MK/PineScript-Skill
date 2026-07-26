# Changelog

## [Unreleased]
- (nothing yet)

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
