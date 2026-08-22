# Changelog

## [Unreleased]
- (nothing yet)

## [0.2.1] - 2026-08-22
### Changed
- The footprint-history trim no longer assigns the shifted bar to a variable nothing reads. The `array.shift()` call still runs; only the pretence that its result mattered is gone. Found by PINE051.

## [0.2.0] - 2026-08-22
### Added
- "Color Bars By Delta" tints each candle by whether buying or selling dominated inside it. The CVD and delta plots stay in the data window because their scale is volume, not price — a real CVD pane needs `overlay=false`, which would mean giving up the footprint. Bar colouring is the honest overlay-compatible answer.

## [0.1.2] - 2026-08-19
### Fixed
- The volume profile never appeared on the chart. The per-bar memoisation guard was `vpCachedBar != bar_index` on a variable starting at `na`, and Pine does not compare reliably against `na` — so the condition was never true, the scan never ran, and the draw block was never entered. Now guarded with `na()`.

### Changed
- "Bars To Draw" now goes up to 30 (was 15). Because boxes are capped at 500 for the whole script, the rows per bar are now derived from the remaining budget: the profile claims its rows first, and the footprint shares what is left. Reducing rows beats silently losing the oldest drawings.
- The dashboard gained a "Footprint" row showing the bar x row count actually in use, highlighted when the rows were reduced to fit.
- Fix profile not drawing; raise bar cap to 30

## [0.1.1] - 2026-08-19
### Fixed
- Seconds-based intrabar resolutions are no longer the default. TradingView serves them only to Premium and higher plans, and asking for one on a lower plan fails the ENTIRE script with "This script uses seconds-based timeframes" rather than degrading — so 0.1.0 simply would not load for most users.
- Added an explicit "Allow Seconds-Based Intrabars" input, defaulting OFF. With it off, Auto never selects a seconds resolution and an explicitly chosen one falls back to 1 minute, so the script always loads.
- The dashboard now flags when the intrabar resolution is not actually finer than the chart (the usual result of a low-timeframe chart without seconds data), instead of quietly showing a meaningless one-row footprint.
- Gate seconds intrabars behind a Premium opt-in

## [0.1.0] - 2026-07-27
### Added
- Initial version of Volume Pro, rebuilt from a reversal-plus-volume-profile script into a dedicated volume/order-flow indicator. The reversal lines, RSI boxes, multi-timeframe trend table and background shading are gone.
- Intrabar engine: one `request.security_lower_tf()` tuple call pulls the lower-timeframe bars inside each chart bar, which is what makes buy/sell separation within a single candle possible at all
- Footprint: per-price buy/sell breakdown for the last N bars, opacity carrying relative volume and an outline marking imbalanced rows; the right-most column is the forming bar and updates as trades print
- Delta and cumulative delta (CVD), with the forming bar added on top of the closed total rather than accumulated into it, so nothing is double-counted on bar close
- Volume profile with a buy/sell split derived from where each bar closed inside its range (a real improvement on binary close-vs-open), plus POC and a configurable Value Area
- Live dashboard: price, bar delta, buy share, CVD, relative volume, POC/VAH/VAL, and the live intrabar count so a truncated or unavailable feed is visible rather than silent
- Alerts on delta flips and volume spikes
- Documented honestly that Pine exposes no bid/ask, so the aggressor side is inferred (tick rule or candle direction) and delta is a strong hint rather than a measurement
