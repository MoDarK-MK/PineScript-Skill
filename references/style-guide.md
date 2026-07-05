# Pine Script Style Guide (per TradingView's official style guide)

Source: TradingView Pine Script docs → Writing scripts → Style guide. This file
condenses it into what the linter enforces and what templates follow. When in doubt,
this is the ground truth for "professional-looking" Pine code — not personal taste.

## Naming conventions

- **camelCase** for all identifiers: `ma`, `maFast`, `maLengthInput`, `roundedOHLC()`.
- **SNAKE_CASE** (all caps) for constants: `BULL_COLOR`, `MAX_LOOKBACK`.
- Qualifying suffixes are encouraged when they clarify type/provenance:
  - `...Input` for anything coming from `input.*()` — `maLengthInput`, `bearColorInput`
  - `...Array` for arrays — `volumesArray`
  - `...Color` for colors — `bearColor`
  - `...Table` for tables — `resultsTable`
  - `...PlotID` for the ID returned by `plot()` when it's reused (e.g. in `fill()`)

The linter's naming check (PINE018) is a soft/style-level warning — it flags
`snake_case` or `PascalCase` identifiers, not a hard error, since it can't
perfectly distinguish every context.

## Script section order

Pine's compiler doesn't enforce this, but TradingView's own style guide recommends
this order, and scaffolded templates follow it:

```
<license>                 // e.g. Mozilla Public License comment + © line
//@version=6
<declaration_statement>   // indicator() / strategy() / library()
<import_statements>       // import statements for libraries
<constant_declarations>   // SNAKE_CASE consts, grouped near the top
<inputs>                  // all input.*() calls together
<function_declarations>   // user-defined functions (must be in global scope)
<calculations>             // core logic
<strategy_calls>          // strategy.entry/exit/order/close (strategies only)
<visuals>                 // plot/plotshape/bgcolor/table/line/label/etc.
<alerts>                  // alertcondition(), alert()
```

Standard license header (default unless the user specifies another license):

```pinescript
// This source code is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/
// © <username>
```

## Constants

- Use `SNAKE_CASE`, declare near the top, initialize with a literal or a `const`-
  qualified built-in (e.g. `color.green`).
- Do **not** prefix constants with `var` — `var` exists to avoid re-initialization
  cost for values that change, but constants never change, so `var` only adds
  needless bar-by-bar maintenance overhead.
- Any literal used in more than one place should become a named constant —
  it documents intent and makes the script easier to maintain.

## Inputs

- Group all `input.*()` calls together, near the top (after constants).
- Suffix input variable names with `Input`.
- Use `inline=` to group related inputs on one settings row, and `group=` to
  organize the settings panel into labeled sections once you have more than a
  handful of inputs.

## Spacing

- A space on both sides of all binary operators (`a + b`, `a > b`), except unary
  operators (`-1`, not `- 1`).
- A space after commas and around `=` in named arguments: `plot(series = close)`.

## Line wrapping (this is where Pine's indentation sensitivity bites)

Pine uses indentation to define blocks — a 4-space (or 1-tab) indent starts a new
local block, same as Python. This has a *non-obvious consequence* for wrapping long
lines:

- A wrapped line **not** enclosed in parentheses must use an indentation width that
  is **not** a multiple of 4 — otherwise Pine reads it as a new block rather than a
  continuation. Convention: indent continuations by 1–3 spaces (commonly 2).
- A wrapped line that **is** enclosed in parentheses (typical for a multi-line
  function call) can use *any* indentation, including a multiple of 4, because the
  open paren already tells the compiler this is a continuation.

```pinescript
// NOT in parentheses — must NOT indent by a multiple of 4:
float closeDiff =
  close          // indented by 2 spaces — correct
  - close[1]

// IS in parentheses — multiples of 4 are fine:
plot(
    close, title = "Close",
    color = color.blue,
    linewidth = 2
)
```

The scaffolded templates and the linter's indentation checks (PINE019/PINE020)
assume the parenthesized style for wrapped function calls, since it's the most
forgiving and the one used in TradingView's own examples.

## Vertical alignment

Aligning similar declarations (constants, inputs) with extra spaces is fine and
TradingView does it in its own examples — it makes multi-cursor edits easier. The
linter does not penalize this.

## Explicit typing

Declaring a variable's type explicitly (`float value = ta.sma(close, 20)` instead of
`value = ta.sma(close, 20)`) is optional but recommended — it documents intent and
makes `=` (declaration) visually distinct from `:=` (reassignment). Templates in
this skill use explicit typing for any non-obvious calculation.
