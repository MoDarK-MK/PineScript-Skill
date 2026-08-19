# Changelog

## [Unreleased]
- (nothing yet)

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
