# Design System for Professional-Looking Indicators

Pine Script correctness and Pine Script *visual polish* are separate skills. A
correct indicator with default `plot(value, color=color.blue)` styling reads as an
amateur script; the patterns below are what separate published, well-regarded
scripts from first drafts. All syntax here is verified v6 (method-call dot-syntax
like `t.cell()`, `arr.push()` is confirmed valid in official TradingView examples).

## 1. Theme-aware color, not hardcoded color

Don't hardcode a single color for lines/backgrounds/text — TradingView users switch
between light and dark chart backgrounds, and a color tuned for one looks wrong or
low-contrast on the other. Two approaches, both legitimate:

**A. Give the user an explicit theme picker** (recommended for published scripts —
predictable, and follows the exact pattern TradingView's own style guide
demonstrates with its `getSize()` example):

```pinescript
string THEME_DARK  = "Dark"
string THEME_LIGHT = "Light"
string themeInput = input.string(THEME_DARK, "Theme", options=[THEME_DARK, THEME_LIGHT], group="Appearance")

getBullColor(string theme) =>
    switch theme
        THEME_DARK  => #26A69A
        THEME_LIGHT => #00796B
        => #26A69A

getBearColor(string theme) =>
    switch theme
        THEME_DARK  => #EF5350
        THEME_LIGHT => #C62828
        => #EF5350

color bullColor = getBullColor(themeInput)
color bearColor = getBearColor(themeInput)
```

A ready-to-paste version of these constants and helpers lives in
`references/snippets/color_helpers.pine`. Note that Pine has no local file
imports — copy-paste the snippet, or publish it as a TradingView library for
true cross-script reuse.

**B. Detect the chart background and adapt automatically** using
`chart.bg_color`/`chart.fg_color` (available via the `chart.*` namespace) — less
predictable across custom background colors, so prefer (A) for anything published.

Either way, expose color *inputs* for anything the user might reasonably want to
personalize (`input.color()`), defaulted to your theme's colors — this is what
makes a script feel configurable rather than fixed.

## 2. Use transparency intentionally, not just solid fills

`color.new(baseColor, transparency)` where transparency is 0 (opaque) to 100
(invisible). Layered semi-transparent fills read as more polished than solid blocks:

- Trend/zone backgrounds: 85-92 transparency (barely-there tint, doesn't fight the
  candles for attention)
- Band/channel fills between two plots: 88-95 transparency
- Signal highlight backgrounds (a single bar flash): 70-80 transparency (needs to
  be noticeable but not opaque)

## 3. Professional stats dashboard (table)

A small corner table summarizing key state (trend direction, current value,
signal strength, etc.) is the single biggest visual "this looks premium" signal.
Pattern (confirmed v6 syntax, method-call style):

```pinescript
var table dashboard = table.new(position.top_right, 2, 3, border_width=1)

if barstate.islast
    dashboard.cell(0, 0, "Trend", text_color=chart.fg_color, text_size=size.small)
    dashboard.cell(1, 0, trendUp ? "Bullish" : "Bearish",
         bgcolor=color.new(trendUp ? bullColor : bearColor, 80),
         text_color=trendUp ? bullColor : bearColor, text_size=size.small)
    dashboard.cell(0, 1, "RSI", text_color=chart.fg_color, text_size=size.small)
    dashboard.cell(1, 1, str.tostring(rsiValue, "#.##"), text_size=size.small)
```

Guidelines:
- Build/update the table body only inside `if barstate.islast` (or
  `barstate.islastconfirmedhistory` for a version that doesn't flicker on the
  currently-forming bar) — it only needs to reflect the final state, not repaint
  on every historical bar, which wastes plot/execution budget for no visible gain.
  Remember: tables don't count toward the 64-item plot-count pool, but there's
  still a max of 9 tables on the chart and their cell text should stay readable at
  the default panel width — don't cram more than ~4-6 rows.
- Give the user a `Show Dashboard` boolean input so it can be turned off.
- Keep it to 2-4 columns; a wide table competing with the price axis looks cluttered.
- Use `size.small` or `size.normal` for cell text — `size.large`/`size.huge`
  overwhelm a small corner table.

## 4. Gradient / heatmap coloring for continuous values

`color.from_gradient(value, bottomValue, topValue, bottomColor, topColor)` maps a
continuous series (RSI, momentum, volume delta) to a smooth color ramp instead of a
hard 2-color threshold — reads as more sophisticated for oscillator-style
indicators. Use sparingly: one gradient-colored series per pane is usually the
limit before it becomes visually noisy.

## 5. Consistent palette as named constants

Per the official style guide, declare your palette as `SNAKE_CASE` constants near
the top rather than scattering `color.new(color.blue, 80)` calls throughout:

```pinescript
color BULL_COLOR = #26A69A
color BEAR_COLOR = #EF5350
color NEUTRAL_COLOR = #787B86
color BG_BULL = color.new(BULL_COLOR, 90)
color BG_BEAR = color.new(BEAR_COLOR, 90)
```

This also makes a script trivially re-themeable later — change the constant, not
every call site.

## 6. Signature / watermark cell (optional, tasteful)

A small bottom-corner table cell with the script name + version (pulling from
`version.json` when scaffolded via this skill) is a common professional touch and
useful for the user's own debugging when running multiple versions side by side
during development — not necessary for personal-use scripts, worth it before
publishing:

```pinescript
var table sig = table.new(position.bottom_right, 1, 1)
if barstate.islast
    sig.cell(0, 0, "MyIndicator v" + "1.2.0", text_size=size.tiny, text_color=color.gray)
```

## 7. What to avoid

- Default `plot()` with no `title=`, no explicit color, no `linewidth=` — reads as
  unfinished even if the logic is solid.
- More than ~4-5 simultaneously visible plot lines of similar visual weight — group
  less-important ones behind a "Show advanced" boolean input instead of always-on.
- Pure red/green for bull/bear with full opacity everywhere — it's the most common
  palette and the least distinctive; teal/coral (TradingView's own updated v6
  defaults) or a custom palette reads as more considered.
- Text sizes larger than `size.normal` for anything but a single headline number —
  large table text at small panel widths gets clipped or wraps badly.
