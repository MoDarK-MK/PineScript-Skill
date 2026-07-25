# Changelog

## [Unreleased]
- (nothing yet)

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
