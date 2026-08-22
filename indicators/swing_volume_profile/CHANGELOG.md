# Changelog

## [Unreleased]
- (nothing yet)

## [0.1.0] - 2026-08-22
### Added
- Initial version. A horizontal volume profile built PER SWING rather than over a fixed last-N-bars window, so the profile always describes the leg price is actually in.
- Swings are detected automatically from pivots, with Pivot Length configurable; defaults are tuned for the 5-minute chart (length 10, roughly 50-minute swings).
- Three marker lines per swing, which is the point of the profile: POC (most total volume), Max Buy (most estimated buying) and Max Sell (most estimated selling). They are frequently different rows, and that separation is the signal.
- Each profile row can be split into a sell segment and a buy segment, or drawn as one bar coloured by whichever side dominated.
- Profile can be drawn over the swing (width capped as a share of the swing so it never buries the candles) or to the right of it.
- Summary table showing POC, max buy, max sell, buy share, and the row count actually in use.
- Fully customisable: swing count, rows, width, transparency, line width/style/extend, labels, colours, theme, table position.

### Notes on method
- Buy/sell is estimated from where each bar closed inside its own range (`(close - low) / (high - low)`). Pine exposes no bid/ask, so no script can know the true aggressor; this is the standard approximation for a profile of this kind and is documented in the file header rather than implied.
- `request.security_lower_tf()` was deliberately not used: on a 5-minute chart the finest intrabar resolution available without a Premium plan is 1 minute — five sub-bars per candle, barely better than the range split and far more expensive.

### Performance
- A completed swing's profile is computed once, when the swing closes, and afterwards only repositioned. Only the developing swing is recomputed, and that is memoised per bar rather than per realtime tick.
- Drawings use `var` pools updated with `.set_*()`; nothing is deleted and rebuilt.
- Rows per swing are derived from the remaining box budget, so a high swing count reduces rows instead of silently hitting TradingView's 500-box cap.
