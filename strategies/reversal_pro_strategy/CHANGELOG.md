# Changelog

## [Unreleased]
- (nothing yet)

## [0.1.0] - 2026-07-26
### Added
- Initial version of Reversal Pro Strategy
- Entry signal: the Reversal Pro 0-5 pivot score, taken at the pivot CONFIRMATION bar (never at the pivot bar itself, which would be lookahead)
- Risk-% position sizing off the stop distance, with syminfo.pointvalue and a separate leverage cap
- ATR or percent stop with a minimum-tick floor; TP1/TP2 at R multiples with an optional partial at TP1
- Breakeven and trailing resolved into one ratcheting stop price rather than two competing exit levels
- Filters: direction, HTF trend, volatility regime, session, and a backtest date window
- Backtest-realism dashboard reporting positions taken separately from closed records
