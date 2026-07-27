# Changelog

## [Unreleased]
- (nothing yet)

## [0.2.1] - 2026-07-27
- Fix CE10088/CE10235 in the test block

## [0.2.0] - 2026-07-27
### Visual
- Fixed 9 dashboard cells that rendered black text on a black panel — Pine defaults cell text to black and those cells set no `text_color`, so most of the numbers were invisible on a dark chart
- Dashboard gained a theme picker, a merged title row, a divider between live position state and backtest quality, left/right column alignment, and a default transparency of 15 instead of 85
- Dashboard position is now an input defaulting to top-left, so it no longer sits on top of the Reversal Pro indicator's own table when both are loaded
- Entry markers use `plotshape` instead of `label.new`, which stops them competing with the test-block labels for the finite 500-label pool on a long backtest
- Fixed inverted level emphasis: TP1 was drawn fainter than TP2 despite being the nearer, more actionable target; all three levels now carry an explicit `linewidth` and `display=`

### Correctness
- Every input used as a history offset gained a `maxval`, so a large value can no longer reach past the history buffer and error at runtime
- Fix invisible dashboard text and level emphasis

## [0.1.0] - 2026-07-26
### Added
- Initial version of Reversal Pro Strategy
- Entry signal: the Reversal Pro 0-5 pivot score, taken at the pivot CONFIRMATION bar (never at the pivot bar itself, which would be lookahead)
- Risk-% position sizing off the stop distance, with syminfo.pointvalue and a separate leverage cap
- ATR or percent stop with a minimum-tick floor; TP1/TP2 at R multiples with an optional partial at TP1
- Breakeven and trailing resolved into one ratcheting stop price rather than two competing exit levels
- Filters: direction, HTF trend, volatility regime, session, and a backtest date window
- Backtest-realism dashboard reporting positions taken separately from closed records
