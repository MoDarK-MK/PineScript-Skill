# Changelog

## [Unreleased]
- (nothing yet)

## [0.2.0] - 2026-08-22
### Added
- Price Rows Per Swing now goes to 500, up from 60. Rows are built at the resolution you ask for regardless of how many get drawn, so POC / Max Buy / Max Sell sharpen with every row added.
- Summary table reports rows actually built and the box budget in use, so the two limits that can bite are visible instead of silent.

### Changed
- Rows holding no volume no longer consume a box. At high resolution most rows in a swing are empty, and that is what makes a high row count affordable; the drawing also breaks out of the loop once the budget is gone.
- Swings draw newest first. If the box budget does run out it is now the oldest swing that thins, never the leg price is trading in.
- Rows are no longer capped by a fixed per-swing budget derived from swing count. Only the drawing is rationed now.

### Fixed
- A swing spanning fewer ticks than the requested row count had its range inflated to `mintick * rows`, drawing a profile taller than the swing it described. The floor is one tick, and rows are reduced to the tick count the swing actually spans — invisible at 30 rows, wrong at 500.

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
