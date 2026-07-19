# Changelog

## [Unreleased]
- (nothing yet)

## [0.2.0] - 2026-07-19
- Extracted the reversal engine from the original multi-module indicator (RSI boxes, volume profile, trend table, and background removed)
- Signals now cover the whole chart history (old 300-bar window removed; capped only by TradingView's 500 label/line limit)
- Added a 0-3 strength score per pivot (RSI exhaustion + volume spike + candle confirmation) shown as stars on each label
- Added minimum-score display filter and STRONG bullish/bearish alert conditions
- Whole-chart reversal signals with 0-3 strength scoring

## [0.1.0] - 2026-07-19
### Added
- Initial version of Reversal Pro
