---
name: pine-script-cicd
description: Use this skill whenever the user wants to write, edit, review, version, or ship TradingView Pine Script indicators or strategies — including any mention of "Pine Script", "TradingView indicator", "TradingView strategy", ".pine files", backtesting, position sizing, risk management, stop losses, or requests to set up git/CI/CD, linting, versioning, changelogs, or a release pipeline for indicators. Also trigger when the user asks to "turn this into a real project", wants automated validation before publishing to TradingView, wants a professional/polished-looking indicator (dashboards, theming), wants to turn an indicator into a strategy, or wants a repeatable workflow for maintaining multiple indicators/strategies over time. Make sure to use this even if the user just says "write me an indicator" or "fix my Pine script" — it covers both one-off script writing AND the full repo/lint/version/release workflow.
---

# Pine Script CI/CD

A skill for writing production-quality TradingView Pine Script (v6) indicators and
strategies, and wrapping them in a lightweight "CI/CD"-style workflow: git repo
structure, a 63-rule offline linter, professional visual design, in-script logical
tests, semantic versioning, and an automated release-bundle step.

**Important framing to give the user up front (once, briefly):** TradingView has no
official public compiler CLI or publish API. "CI/CD" here means everything that *can*
be automated locally (structure, lint, tests-as-code, versioning, changelogs, release
packaging) — the final "deploy" step is always a manual paste into the Pine Editor and
click "Add to Chart" / "Publish Script". Don't oversell this as literally connecting to
TradingView's servers.

## Reference files — read before writing/linting nontrivial scripts

| File | Covers |
|---|---|
| `references/volume-keylevels-guide.md` | Institutional guide: Auction Market Theory, Volume Profile, vPOCs, CVD/Delta divergence, Anchored VWAP, and Key Level clustering |
| `references/mtf-guide.md` | `request.security` / `request.security_lower_tf`: the three lookahead combinations, which one is the bug, gaps, the 40-call budget, and what "repaint" actually means |
| `references/alerts-guide.md` | `alertcondition` vs `alert()`, frequency, placeholders, webhook JSON payloads, and why no secret belongs in a message |
| `references/troubleshooting.md` | Symptom-first index of every failure this repo actually hit, with the rule that now catches each one |
| `references/decisions.md` | Decision record: what was decided, why, and what would change our mind |
| `references/pine-v6-guide.md` | v5→v6 breaking changes, dynamic requests, repainting traps, `var`/`varip`, verified hard platform limits |
| `references/style-guide.md` | Official naming/structure/spacing conventions (camelCase, SNAKE_CASE, section order, line-wrapping) |
| `references/lint-rules.md` | Full catalog of all 63 lint rules (codes PINE001–PINE064; PINE024 unassigned) with bad/good examples |
| `references/design-system.md` | Making indicators look professional: theming, dashboards, gradients, palettes |
| `references/strategy-guide.md` | Building strategies: signal design, position sizing math, the four risk modules, filters, overfitting, walk-forward, v6 strategy pitfalls |
| `references/publishing-guide.md` | TradingView House Rules condensed: privacy/visibility, strategy realism, description format |
| `references/repo-structure.md` | Folder layout, `version.json`, `CHANGELOG.md` format, optional pre-commit hook |
| `references/performance-guide.md` | Work tiering, memoization, buffer reuse, drawing pools, `var` vs `varip` |
| `references/snippets/` | Copy-paste Pine fragments for the parts a library cannot hold: `table_helpers.pine`, `glyphs.pine`, `live_update.pine`, `palette.pine`, `volume_levels_engine.pine`, `anchored_vwap.pine`, `key_levels_cluster.pine`. Pine has no local imports, so stateful helpers are pasted |
| `libraries/pine_toolkit/` | The pure helpers as a real Pine `library()`: theme palette, `formatVolume`, `glyphMeter`, `clamp`/`safeDiv`/`positionBetween`/`buyShare`, `effortResultRatio`, `isVolumeClimax`, `isLowVolumeTest`, `inValueArea`, `scoreKeyLevel`, `detectDeltaDivergence`, constant mappers. Publish it once, then `import` instead of pasting |

Several of these apply to any single request — e.g. "write me an indicator" still
benefits from `pine-v6-guide.md` (correctness) and `design-system.md` (it not looking
like a first draft), even with no repo/versioning involved.

## When to use which part

- User wants a single indicator/strategy written or fixed quickly → **Writing the
  script** + **Linting**, skip repo scaffolding unless they ask for it.
- User wants a proper ongoing project ("set up a repo", "CI/CD", "versioning") → the
  full flow: **Scaffold → Write → Lint → Test → Version → Release bundle**.
- User has an existing project already using this structure → find `version.json`
  and `CHANGELOG.md` in their repo and continue from wherever they left off.

## Repo structure

Every indicator or strategy lives in its own folder (full rationale in
`references/repo-structure.md`):

```
project-root/
├── indicators/<name>/{src/<name>.pine, version.json, CHANGELOG.md}
├── strategies/<name>/  (same shape)
└── .pine-lint.json   (optional shared lint config overrides)
```

Where a workspace has them, an indicator and its strategy counterpart
can share one scoring engine, used both
ways — read them side by side when you need a concrete reference.

Scaffold a new one (pre-fills the professional template, `version.json` at `0.1.0`,
and an initial `CHANGELOG.md`):

```bash
python3 scripts/scaffold_project.py --kind indicator --name my_rsi_bands --out ./indicators --title "My RSI Bands"
python3 scripts/scaffold_project.py --kind strategy --name trend_break --out ./strategies --title "Trend Break"
```

## Writing the script

Always target **Pine Script v6** (`//@version=6`) unless the user explicitly says v5
or you detect an existing file starting with `//@version=5` — match the existing
version rather than silently upgrading it (v6 changes `strategy()` margin defaults,
removes `when=`/`transp=`, tightens `switch`/history-referencing rules, etc. — see
`references/pine-v6-guide.md` §2 before touching an existing v5 file).

Start from `assets/templates/` rather than a blank file — every template already
follows the official section order (license → version → declaration → constants →
inputs → functions → calculations → visuals → alerts), uses a theme-aware color
system, a corner stats dashboard, and a debug/test toggle:

- `indicator_template.pine` — theme picker, dashboard, alertcondition, test block
- `strategy_template.pine` — a full risk-management skeleton with a placeholder
  signal; see **Building strategies** below
- `dashboard_block_template.pine` / `test_block_template.pine` — standalone, runnable
  reference snippets for the dashboard pattern and the assertion-counter test
  pattern, meant to be copy-pasted from rather than scaffolded whole

For visual polish beyond the templates' defaults, read
`references/design-system.md` — a correct-but-default-styled script reads as an
unfinished first draft. The one defect worth knowing before you write a single
table: **`table.cell()` with no `text_color=` renders BLACK**, which is invisible
on a dark chart. It looks fine to whoever wrote it on a light theme and it is
silent. Use a row builder that takes the colors as required arguments
(`references/snippets/table_helpers.pine`); PINE036 enforces it.

## Keeping scripts fast and live

Users expect a dashboard to track price tick-by-tick. The trap is that
`if barstate.islast` runs on **every realtime tick, not once per bar** — so a
long scan placed there can run several times a second against a 500 ms-per-loop
cap. Read `references/performance-guide.md` before writing anything with a loop.

The rule that resolves it: **display updates every tick, computation does not.**
Fingerprint whatever a heavy result depends on and rebuild only when that moves,
while the drawings keep repositioning live:

```pinescript
if barstate.islast
    if cachedLeft != leftBar or cachedRight != rightBar   // the scan is gated
        cachedLeft := leftBar, cachedRight := rightBar
        cachedPoc  := expensiveScan(leftBar, rightBar)
    box.set_rightbottom(zoneBox, bar_index, cachedPoc)    // the drawing is not
```

Three more habits worth having, each with a lint rule behind it: reuse one `var`
array with `array.fill()` instead of allocating per tick (PINE037), move drawings
with `.set_*()` instead of delete-and-recreate (PINE038), and merge
`request.security()` calls that share symbol + timeframe + lookahead (PINE039).
Give every input used as a history offset a `maxval`, or a large value produces a
runtime error that reads like a script bug.

**When the user asks for a "Heavy Script", "High-Performance Script", or complains about speed:**
- Always default to the fingerprint caching pattern.
- Combine this with pooling (`var array`), and restrict intensive ops to `barstate.isconfirmed` where possible.
- Hide intermediate plots using `display=display.none` to prevent Status Line clutter.
- Add visual polish natively: Use `color.from_gradient` for varying densities instead of solid colors.

A completed indicator project in the workspace is the worked example of all of this.

Before shipping anything, `python3 scripts/doctor.py --fast` runs every check
this repo has and gives one verdict. It names any check it had to skip rather
than counting it as a pass.

## Building strategies

Reach for a strategy when the user wants **backtested results** — P&L, win rate,
drawdown. If they only want to be told when something happens, an indicator with
`alertcondition()` is simpler, has no sizing assumptions to get wrong, and is far
easier to publish. Turning an indicator into a strategy adds a claim ("I took this
much risk and this is what happened") that has to be defensible.

Read `references/strategy-guide.md` before writing anything nontrivial. The one
idea that matters most: a complete trade is **entry + invalidation + objective**,
not just an entry. "Buy the cross up, sell the cross down" has no invalidation, so
risk is unbounded and position sizing is meaningless.

`assets/templates/strategy_template.pine` ships the machinery with a placeholder
EMA-cross signal — replace the signal block, keep the rest. Its four risk modules,
one input group each:

- **Position Sizing** — risk-% of equity per trade, sized off the stop distance,
  with `syminfo.pointvalue` (mandatory for futures) and a separate leverage cap
- **Stops & Targets** — ATR or percent stop with a minimum-tick floor, TP1/TP2 at
  R multiples, optional partial exit at TP1
- **Breakeven & Trailing** — resolved into **one** ratcheting stop price, not two
  competing `strategy.exit` levels (in v6 whichever triggers first wins, so two
  mechanisms in one exit interact unpredictably)
- **Session & Date Window** — session and timezone filtering, plus a date window
  that doubles as the in-sample/out-of-sample control for walk-forward testing

```bash
python3 scripts/scaffold_project.py --kind strategy --name trend_break --out ./strategies --title "Trend Break"
```

**A strategy that looks good in the Strategy Tester is the default outcome, not
evidence.** Before showing a user an equity curve, check the trade count (100+, and
count *positions* — partial exits roughly double `strategy.closedtrades`), whether
the date window was tuned after the fact, and whether the result survives moving
the stop multiple ±25%. Say so plainly when it doesn't.

PINE029–PINE035 fire only on strategies (level-less exits, mixed relative/absolute
levels, tick-vs-price units, unguarded `position_avg_price`, bad `qty`, orphan
`from_entry`, entries with no exit). `generate_release_bundle.py` adds a realism
gate for `"kind": "strategy"` projects — lookahead bias, synthetic chart types, and
zero-cost backtests block the release outright.

## Engineering Volume & Key Level Indicators

When the user asks to build indicators or strategies based on **Volume**, **Order Flow**,
**Volume Profile**, **vPOCs**, **Anchored VWAP**, or **Key Levels / Liquidity Sweeps**:

1. **Follow Auction Market Theory (AMT)**: Read `references/volume-keylevels-guide.md`.
   - Calculate exact Value Area (70% Volume) and Point of Control (POC).
   - Track **Virgin / Naked POCs (vPOC)** in dynamic arrays and prune them as soon as price tests/mitigates them (`low <= vpoc && high >= vpoc`).
2. **Order Flow & Delta Aggressor Modeling**:
   - Use normalized range models `buyShare = (close - low) / (high - low)` for fast single-bar delta, or `request.security_lower_tf()` for high-precision intrabar delta (with seconds-fallback safety).
   - Compute Cumulative Volume Delta (CVD) and evaluate Regular/Hidden Delta Divergence at swing highs/lows.
   - Detect **Volume Absorption** via Effort vs Result (EVR = Normalized Volume / Normalized Spread > 2.2).
3. **Anchored VWAP & Statistical Dispersion**:
   - Accumulate typical price $\times$ volume, total volume, and squared price $\times$ volume to calculate rolling VWAP and exact $\pm 1\sigma, \pm 2\sigma$ dispersion bands without loop overhead.
4. **Key Level Clustering & Liquidity Sweeps**:
   - Fetch HTF levels (PDH, PDL, PWH, PWL) with zero lookahead (`lookahead=barmerge.lookahead_off`, `high[1]`/`low[1]`).
   - Detect false breakouts / liquidity sweeps: price pierces a key level but closes back inside with volume expansion ($\ge 1.8\times \text{SMA}_{20}$).
   - Cluster close proximity levels into single weighted Confluence Zones to avoid chart clutter and prevent exceeding drawing limits.
5. **Drawing & Performance Discipline**:
   - Declare pre-allocated array memory pools (`var float[]`) instead of reallocating in loops.
   - Restrict heavy recalculations in `barstate.islast` using input fingerprint caching.
   - Manage drawing pools to strictly respect the 500 boxes/lines/labels limit.

## Linting (the "CI" part)

`scripts/pine_lint.py` is a rule-based, OFFLINE linter — it does NOT compile the
script (no such public tool exists). All 63 rules are fact-checked against
TradingView's official docs (migration guide, limitations page, style guide) as of
mid-2026; full catalog with examples in `references/lint-rules.md`. Highlights:

- Hard v6 compile errors: `when=`/`transp=` (removed), `linewidth<1`, `switch` missing
  a default arm, history-referencing `[]` on a literal, duplicate named parameters,
  indicator/strategy with no output-producing call, mixed-tab/space indentation, a
  block header (`if`/`for`/`while`/`switch`/`=>`) with no indented body
- Real behavior traps: `and`/`or` lazy-evaluation, `timeframe.period` bare-unit
  comparisons, `request.security()` missing `lookahead=`, accumulators missing `var`
- Style: naming convention, line length, missing input titles, missing `overlay=`
- Approaching/over the real platform limits (64 plot-count pool; 500 lines/boxes/
  labels; 100 polylines; 9 tables)

```bash
python3 scripts/pine_lint.py path/to/script.pine          # human-readable
python3 scripts/pine_lint.py path/to/script.pine --json    # machine-readable
python3 scripts/pine_lint.py path/to/script.pine --strict  # warnings also fail
python3 scripts/pine_lint.py --list-rules                  # print the full catalog
```

Suppress a specific finding inline when it's a deliberate choice, not a bug:
`// pine-lint-disable-next-line PINE008`, `// pine-lint-disable-line PINE008`, or a
file-wide `// pine-lint-disable PINE018,PINE008` comment anywhere in the file.

Exit code 0 = no errors (warnings/notes may still print; `--strict` also fails on
warnings). Treat lint as a gate: don't hand a script back as "done" with unresolved
errors — fix them, then re-run. Warnings are judgment calls; mention them to the user
rather than silently ignoring or silently auto-fixing.

## In-code logical tests (the "test" part)

Since Pine Script has no external unit-test runner, tests live *inside* the script,
gated behind a `Test Mode` input so they never affect normal chart use.
`assets/templates/test_block_template.pine` demonstrates the pattern this skill uses:
an **assertion counter** (`passCount`/`failCount` tallied in a small table) rather
than one label per check — a long backtest with dozens of failing bars would
otherwise burn through the label/plot-count budget just from the test scaffolding
itself. Every scaffolded template already wires up a couple of starter assertions;
extend them with checks specific to the script's own logic.

When the user asks for "tests", generate 3-6 concrete assertions covering: a normal
case, a boundary case (e.g. `bar_index == 0`, `na` inputs), and one case that would
catch the most likely bug for that specific indicator's logic (e.g. division by zero
in a ratio, off-by-one in a lookback). Explain in plain language what each one checks.
**Never leave a `testMode`-style input defaulting to `true`** — `generate_release_bundle.py`
(below) checks for this automatically before a release is considered ready.

## Versioning and changelog

Semantic versioning (`MAJOR.MINOR.PATCH`) tracked in each project's `version.json`.
PATCH = bug/lint fix, no behavior change. MINOR = new input/plot/alert, backward-
compatible. MAJOR = changes existing plot values/alert conditions/default behavior.

```bash
python3 scripts/bump_version.py path/to/project --bump patch --note "Fixed off-by-one in lookback"
```

Updates `version.json` and moves `## [Unreleased]` to a dated `## [x.y.z] - YYYY-MM-DD`
entry in `CHANGELOG.md`, adding a fresh empty `[Unreleased]` above it. Format details
in `references/repo-structure.md`.

## Release bundle ("CD" part)

`scripts/generate_release_bundle.py` automates the release checklist instead of
leaving it as a manual list — run it once lint is clean and the version is bumped:

```bash
python3 scripts/generate_release_bundle.py path/to/project [--out path/to/release] [--strict]
```

It writes three files to `<project>/release/` (or `--out`):
- **`<name>.pine`** — final source, with a Mozilla Public License header added
  automatically if the file doesn't already have one
- **`PUBLISH_DESCRIPTION.md`** — a drafted TradingView publish-description scaffold
  (purpose / how it works / how to use it / originality, plus a backtest-realism
  disclosure section for strategies) structured per `references/publishing-guide.md`
  — Claude should fill in the bracketed placeholders using the script's actual logic
  before handing it to the user, not leave them as literal placeholder text
- **`RELEASE_SUMMARY.txt`** — full lint output, whether a test-mode input was caught
  defaulting to `true`, whether a license header was added, and a final
  READY/NOT-READY verdict (exit code 0 only if ready, or all-clear under `--strict`)

There is still no publish API — the user pastes `<name>.pine` into the Pine Editor
and goes through TradingView's own "Publish script" UI manually, using
`PUBLISH_DESCRIPTION.md` as a starting point for the description field. Point out the
15-minute public-edit window from `references/publishing-guide.md`: publish a private
draft first, verify it, then make it public.

## Git workflow (optional, if the user wants a real repo)

If the user wants git integration, set up (or tell them to run, since Claude cannot
execute `git init`/`commit` on the user's actual machine unless they're working in
this same sandboxed environment):

```bash
git init && git add . && git commit -m "chore: scaffold <name>"
```

Suggest the pre-commit hook in `references/repo-structure.md` (lints staged `.pine`
files before allowing a commit) if they want the linter enforced automatically.

## Communicating with the user

Most people asking for this are traders, not software engineers. Avoid unexplained
jargon like "semver" or "CI/CD gate" on first use — say "version numbering" or
"automatic check" and mention the technical term in parentheses. Always be upfront,
once, that the lint/test steps are Claude-side offline checks, not a connection to
TradingView's real compiler — this sets accurate expectations about what "passing"
actually guarantees.
