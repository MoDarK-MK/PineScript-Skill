---
name: pine-script-cicd
description: Use this skill whenever the user wants to write, edit, review, version, or ship TradingView Pine Script indicators or strategies — including any mention of "Pine Script", "TradingView indicator", "TradingView strategy", ".pine files", or requests to set up git/CI/CD, linting, versioning, changelogs, or a release pipeline for indicators. Also trigger when the user asks to "turn this into a real project", wants automated validation before publishing to TradingView, wants a professional/polished-looking indicator (dashboards, theming), or wants a repeatable workflow for maintaining multiple indicators/strategies over time. Make sure to use this even if the user just says "write me an indicator" or "fix my Pine script" — it covers both one-off script writing AND the full repo/lint/version/release workflow.
---

# Pine Script CI/CD

A skill for writing production-quality TradingView Pine Script (v6) indicators and
strategies, and wrapping them in a lightweight "CI/CD"-style workflow: git repo
structure, a 27-rule offline linter, professional visual design, in-script logical
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
| `references/pine-v6-guide.md` | v5→v6 breaking changes, dynamic requests, repainting traps, `var`/`varip`, verified hard platform limits |
| `references/style-guide.md` | Official naming/structure/spacing conventions (camelCase, SNAKE_CASE, section order, line-wrapping) |
| `references/lint-rules.md` | Full catalog of all 27 lint rules (codes PINE001–PINE028; PINE024 unassigned) with bad/good examples |
| `references/design-system.md` | Making indicators look professional: theming, dashboards, gradients, palettes |
| `references/publishing-guide.md` | TradingView House Rules condensed: privacy/visibility, strategy realism, description format |
| `references/repo-structure.md` | Folder layout, `version.json`, `CHANGELOG.md` format, optional pre-commit hook |
| `references/snippets/` | Copy-paste Pine fragments (e.g. `color_helpers.pine` — theme color constants/helpers). Pine has no local imports; paste, or publish as a TradingView library for real reuse |

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
- `strategy_template.pine` — same, plus realistic risk-management inputs
  (stop/take-profit %), `alert_message=` JSON wired to TradingView's own alert
  placeholders (`{{ticker}}`, `{{close}}`, `{{time}}`), and a position/P&L dashboard
- `dashboard_block_template.pine` / `test_block_template.pine` — standalone, runnable
  reference snippets for the dashboard pattern and the assertion-counter test
  pattern, meant to be copy-pasted from rather than scaffolded whole

For visual polish beyond the templates' defaults (multi-color gradients, watermark
cells, transparency conventions), read `references/design-system.md` — a
correct-but-default-styled script reads as an unfinished first draft.

## Linting (the "CI" part)

`scripts/pine_lint.py` is a rule-based, OFFLINE linter — it does NOT compile the
script (no such public tool exists). All 27 rules are fact-checked against
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
