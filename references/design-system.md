# Design System for Professional-Looking Indicators

Pine Script correctness and Pine Script *visual polish* are separate skills. A
correct indicator with default `plot(value, color=color.blue)` styling reads as an
amateur script; the patterns below are what separate published, well-regarded
scripts from first drafts. All syntax here is verified v6 (method-call dot-syntax
like `t.cell()`, `arr.push()` is confirmed valid in official TradingView examples).

Ready-to-paste implementations live in `references/snippets/`:
`palette.pine`, `table_helpers.pine`, `glyphs.pine`, `live_update.pine`.

---

## 0. The one that breaks scripts: cell text defaults to BLACK

`table.cell()` with no `text_color=` renders black. Over a dark panel or a dark
chart that cell is **invisible**. It is the single most common visual defect in
Pine, it looks fine to whoever wrote it on a light chart, and it is silent.

```pinescript
// bad — invisible on TradingView's default dark theme
t.cell(1, 1, str.tostring(maValue, "#.##"), text_size=size.small)

// good
t.cell(1, 1, str.tostring(maValue, format.mintick), text_color=textColor, text_size=size.small)
```

Set `text_color` on **every** cell that shows text. The reliable way to guarantee
that is a row builder that takes the colors as required arguments, so a caller
physically cannot omit them — see §3 and `snippets/table_helpers.pine`. Lint rule
**PINE036** enforces this.

## 1. Theme-aware color, not hardcoded color

TradingView users switch between light and dark chart backgrounds, and a color
tuned for one looks wrong or low-contrast on the other.

**Give the user an explicit theme picker.** This is more predictable than reading
`chart.bg_color`/`chart.fg_color`, which vary with custom backgrounds, and it
follows the pattern TradingView's own style guide demonstrates:

```pinescript
string THEME_DARK  = "Dark"
string THEME_LIGHT = "Light"
string themeInput = input.string(THEME_DARK, "Theme", options=[THEME_DARK, THEME_LIGHT], group="Appearance")

getBullColor(string theme) =>
    switch theme
        THEME_LIGHT => #00796b
        => #089981

getBearColor(string theme) =>
    switch theme
        THEME_LIGHT => #c62828
        => #f23645
```

**A theme is not just two accents.** The common failure is shipping a theme
picker that only drives one `plot()` color while the dashboard stays hardcoded.
A complete theme covers five roles:

| Role | Purpose |
|---|---|
| bull / bear accent | directional values |
| primary text | the value column — reads first |
| muted text | the label column — deliberately lower contrast |
| panel background | table fill |
| divider / frame | borders and section separators |

All five are in `snippets/palette.pine`. Use one palette per repo — two competing
bull/bear pairs across files is a tell that nobody owns the visual system.

Expose color *inputs* for anything a user might reasonably personalise
(`input.color()`), defaulted to the theme's colors.

## 2. Typography and hierarchy

Three weights is enough for any dashboard, and fewer than three reads as a data
dump rather than a design:

1. **Title** — `size.normal`, primary text color, one per table.
2. **Label** — `size.small`, muted color, left-aligned.
3. **Value** — `size.small`, primary or accent color, right-aligned.

**Never go above `size.normal` for chart text.** `size.large`/`size.huge` clip or
wrap badly at real panel widths — lint rule **PINE041**. The exception is a
single headline number that is the whole point of the script.

Color carries hierarchy better than size does. A muted label next to a
full-contrast value separates the two without changing a single font size.

## 3. Table anatomy

```pinescript
var table dashboard = table.new(
     tablePosFrom(tablePosInput), 2, 4,
     bgcolor=getPanelColor(themeInput, 15),
     border_color=getPanelColor(themeInput, 100), border_width=1,
     frame_color=color.new(mutedColor, 70), frame_width=1)

if showDashboardInput and barstate.islast
    // Title row: fill the first cell, THEN merge. Merging an empty cell drops the text.
    table.cell(dashboard, 0, 0, "MY INDICATOR", text_color=textColor,
         text_size=size.normal, text_halign=text.align_center)
    table.cell(dashboard, 1, 0, "", text_color=textColor)
    table.merge_cells(dashboard, 0, 0, 1, 0)
    dashRow(dashboard, 1, "Trend", trendUp ? "Bullish" : "Bearish", mutedColor,
         trendUp ? bullColor : bearColor)
    dashRow(dashboard, 2, "MA", str.tostring(maValue, format.mintick), mutedColor, textColor)
```

- **Alignment**: labels `text.align_left`, numbers `text.align_right`. Centred
  numbers jitter horizontally as digits are added and removed on each tick —
  right-aligning them makes the column stable and instantly more professional.
- **Transparency 10–25**, not 80. At 85 the candles behind the panel win and the
  numbers stop being readable. This is the second most common dashboard defect
  after missing `text_color`.
- **Row count**: aim for 4–8. Past that, add a divider row
  (`table.cell(t, c, row, "", height=0.4, bgcolor=dividerColor)`) to separate
  logical groups, or drop rows. An 11-row undifferentiated wall is not a
  dashboard, it's a log.
- **Position should be an input.** Two scripts that both hardcode
  `position.top_right` will sit on top of each other. There are only 9 slots.
- **Update in place when only values change**: `table.cell_set_text()` /
  `cell_set_text_color()` beats rebuilding every cell each tick.

## 4. Label placement and overlap

The default is that labels collide. N horizontal levels anchored at the same
`bar_index` will stack on top of each other whenever their prices cluster —
PDH next to a swing high, CDL next to PDL.

- Use `label.style_label_lower_left` (or `_upper_left`) so the text floats
  **beside** the line rather than sitting on it, where the line cuts the text.
- **Nudge apart when crowded.** Sort by price, walk the list, and push each label
  down when the gap to the previous one is under a threshold — a fraction of ATR
  works well because it scales with the instrument:

```pinescript
array<int> order = array.sort_indices(lvlPrices, order.descending)
float minGap = atrValue * 0.35
float lastY  = na
for k = 0 to levelCount - 1
    float p = array.get(lvlPrices, array.get(order, k))
    float labelY = p
    if not na(lastY) and (lastY - labelY) < minGap
        labelY := lastY - minGap
    lastY := labelY
    // the LINE stays at the true price p; only the label text moves
```

- Keep label families consistent: if reversal labels, level labels and zone
  labels all anchor near `bar_index`, decide a shared placement policy rather
  than letting three independent rules fight.

## 5. Transparency conventions

| Element | Transparency |
|---|---|
| Table panel background | **10–25** |
| Trend/zone background fills | 85–92 |
| Band/channel fills | 88–95 |
| Single-bar signal flash | 70–80 |
| Tinted verdict cell background | 80–90 |
| Label text | **0–30** |

Label text above ~30 transparency with no backing plate is unreadable over candle
wicks. If a signal is weak enough to warrant fading, fade it to 30, not 50.

## 6. Gradients

`color.from_gradient(value, bottomValue, topValue, bottomColor, topColor)` maps a
continuous series to a smooth ramp instead of a hard two-color threshold — good
for RSI, momentum, volume delta. It turns a number into a reading.

One gradient-colored series per pane is the limit before the chart looks like a
heat map. A gradient in a **table cell** is often better than one on the chart:
it colors the value the eye is already reading.

## 7. `display=` and layering

`display=` is how you stop a plot polluting every surface at once:

```pinescript
plot(stopPrice, "Stop", display=display.pane + display.price_scale)
```

Options combine with `+`: `display.pane`, `display.price_scale`,
`display.status_line`, `display.data_window`, `display.all`, `display.none`.

A level series that is `na` most of the time has no business in the status line —
it shows as a permanent blank. Use `display.none` for values plotted purely so
they can be referenced by an alert or another script.

## 8. Drawing cleanup and object budget

Lines, boxes and labels cap at **500 IDs each**, and only the last 50 show by
default (raise with `max_lines_count` / `max_boxes_count` / `max_labels_count`).
Setting a drawing's property to `na` still consumes its ID — delete it, or don't
create it.

Objects created per qualifying bar and never deleted will exhaust the pool on a
long history, after which the oldest silently vanish. That reads as a bug to
users, because it is one.

For anything redrawn on the last bar, **move the object instead of recreating
it** — see `references/performance-guide.md` §5. That is both a performance and
a visual fix: churned drawings flicker.

## 9. Glyph conventions

Use named constants (`snippets/glyphs.pine`) rather than literals scattered
through the file: `★ ☆ ▲ ▼ ✔ ✘ ↑ ↓`.

Full-width glyphs (`★ ▲ ●`) and narrow ones (`✔ ↑ –`) don't align with each
other. Pick one width family per column you want aligned.

## 10. What to avoid

- A bare `plot()` with no `title=` — it shows as an unnamed entry in the settings
  panel, data window and status line (**PINE040**). No `linewidth=` reads as
  unfinished too.
- More than 4–5 plotted lines of the same visual weight — nothing reads as
  primary.
- Pure `color.red`/`color.green`/`color.gray` named colors mixed with a hex
  palette in the same file. Pick the palette.
- Text sizes above `size.normal` (**PINE041**).
- A theme picker that doesn't reach the dashboard (§1).
- A panel at 85 transparency (§3).
