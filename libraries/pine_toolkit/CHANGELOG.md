# Changelog

## [Unreleased]
- (nothing yet)

## [0.1.0] - 2026-08-22
### Added
- Initial version of PineToolkit, the shared helper library.
- Theme palette (`textColor`, `mutedColor`, `panelColor`, `bullColor`, `bearColor`, `accentColor`), formatting (`formatVolume`, `formatPercent`, `glyphMeter`), maths (`clamp`, `safeDiv`, `positionBetween`, `buyShare`) and the constant mappers (`lineStyleFrom`, `sizeFrom`).
- Scope is deliberately narrow: pure functions only, no inputs, no drawings, no `request.*()`, no `var` state. Pine restricts what a library may contain, and a pure function is the part that is unambiguously allowed — a stateful helper shared by four scripts would be a worse problem than the duplication it replaces.
- Self-check plots: a library cannot be unit-tested offline, so it asserts its own invariants into the data window. Load it once and every one must read 1.
