# 🎯 Pine Script Skill
> **Production-Grade TradingView Pine Script Indicators & Strategies**

[![License: MPL 2.0](https://img.shields.io/badge/License-MPL%202.0-brightgreen.svg)](https://opensource.org/licenses/MPL-2.0)
[![Pine Script v6](https://img.shields.io/badge/Pine%20Script-v6-1f51b6.svg)](https://www.tradingview.com/)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-3776ab.svg)](https://www.python.org/)

Transform your TradingView Pine Script ideas into **production-ready indicators and strategies** with professional tooling, automated linting, structured versioning, and release pipelines—all without leaving your editor.

## ✨ What Makes This Different

Most Pine Script traders treat each indicator as a one-off script. Pine Script Skill treats them like **real projects**:

- 🔍 **59-Rule Linter** — v6 compile errors, repainting traps, scope violations, performance costs, invisible dashboard text. Seven rules repair themselves with `--fix`
- ▶️ **It Runs The Code** — a Pine interpreter in Python executes a script offline, bar by bar, with real series history. Not a lint pass: actual execution, with parameter sweeps and every approximation reported
- 🧠 **Real Static Analysis** — A symbol table catches `:=` to an undeclared name (TradingView's `Undeclared identifier`) and variables written but never read. Loop nests are costed at their worst case against Pine's 500 ms limit
- 🎨 **Formatter** — `pine_fmt.py --check` in CI. It never touches block indentation, because in Pine that is structure, not style
- 📋 **Professional Templates** — Scaffold indicators/strategies with theme-aware dashboards, test blocks, and best-practice structure
- 🛡️ **Strategy Risk Modules** — Risk-% sizing, ATR stops, breakeven + trailing, TP1/TP2 partials, session and date-window filters, account-level guards — wired together and ready to use
- ✅ **In-Script Testing** — Assertions inside your Pine code; results show in a test-mode table
- 🧬 **Tests That Are Themselves Tested** — `mutate_check.py` disables each lint rule and confirms the suite goes red. Its first run found 16 of 59 rules with no test at all
- 📦 **Automated Releases** — Lint report, version bump, changelog, git tag, publish description, and a generated table of every setting
- ⚡ **Live & Fast** — Work-tiering and memoization so a dashboard tracks price tick-by-tick without re-running heavy scans
- 📚 **12 Reference Guides** — including a multi-timeframe guide, a symptom-first troubleshooting index, and a decision record

Perfect for traders who want **repeatable workflows** across multiple indicators, not just quick one-offs.

### What this does *not* do

TradingView publishes no compiler CLI or API, so **nothing here can guarantee a
script compiles**. The linter matches patterns; it does not parse a syntax tree.
Every rule in it was either read out of TradingView's own docs or added *after*
a real paste failed — and when one gets missed, the fix is a new rule plus a
fixture in `tests/fixtures/compile_errors/`, not a louder claim. See
[decisions.md](references/decisions.md) D10.

---

## 🚀 Quick Start

### 1. Clone & Explore
```bash
git clone https://github.com/MoDarK-MK/PineScript-Skill.git
cd PineScript-Skill
```

### 2. Scaffold Your First Indicator
```bash
python3 scripts/scaffold_project.py --kind indicator --name my_rsi_bands --title "My RSI Bands"
```
This generates:
- Professional template with theme picker, dashboard, test block
- `version.json` tracking (starting at v0.1.0)
- Empty `CHANGELOG.md` ready to fill in

### 3. Write Your Logic
Edit `indicators/my_rsi_bands/src/my_rsi_bands.pine` with your indicator code.

### 4. Lint & Format Before Publishing
```bash
python3 scripts/pine_lint.py indicators/my_rsi_bands/src/my_rsi_bands.pine
python3 scripts/pine_lint.py indicators/my_rsi_bands/src/my_rsi_bands.pine --fix
python3 scripts/pine_fmt.py  indicators/my_rsi_bands/src/my_rsi_bands.pine
```
Catches v6 errors, repainting traps, scope violations, performance issues and
style problems — **offline, no TradingView compiler needed**. `--fix` repairs
the six rules that have exactly one correct rewrite; anything needing intent
stays a finding, because a linter that guesses is worse than one that nags.

### 5. Test Your Logic
Add assertions to the `Test Mode` block in your script, then toggle `Test Mode = true` in TradingView. Results appear in a table; no test framework to learn.

### 6. Version & Release
```bash
python3 scripts/bump_version.py indicators/my_rsi_bands --bump minor --note "Added smoothing input"
python3 scripts/generate_release_bundle.py indicators/my_rsi_bands
```
Outputs:
- Linted `.pine` file with MPL 2.0 header
- Pre-filled TradingView publish description
- `INPUTS.md` — every setting with its default, range and explanation
- Release checklist summary with a READY / NOT READY verdict

The bump also creates an annotated git tag `my_rsi_bands/v0.2.0`, namespaced per
project so several can share one repo.

### 7. Publish to TradingView
Paste the `.pine` file into the Pine Editor, use the generated description, publish. Done.

---

## 📦 Projects

<!-- BEGIN GENERATED: projects -->
| Project | Kind | Version | Lines | Lint | What it is |
|---|---|---|---|---|---|
| [`pine_toolkit`](libraries/pine_toolkit/) | library | `0.1.0` | 192 | clean | Initial version of PineToolkit, the shared helper library. |

*1 project(s). Generated by `scripts/build_index.py`.*
<!-- END GENERATED: projects -->

> `pine_toolkit` is the shared helper library. `scaffold_project.py` creates your
> own projects alongside it — this repository ships the **toolchain**, and the
> indicators you build with it are yours.

## 📁 Project Structure

<!-- BEGIN GENERATED: tree -->
```
PineScript-Skill/
├── libraries/pine_toolkit/  # v0.1.0 (library)
├── scripts/
│   ├── backup_private.py
│   ├── build_fa_reference.py
│   ├── build_index.py
│   ├── build_pine.py
│   ├── bump_version.py
│   ├── check_budget.py
│   ├── check_inputs_compat.py
│   ├── check_library_sync.py
│   ├── complexity.py
│   ├── doctor.py
│   ├── generate_release_bundle.py
│   ├── input_inventory.py
│   ├── install_hooks.py
│   ├── lint_all.py
│   ├── mutate_check.py
│   ├── new_rule.py
│   ├── pine_edit.py
│   ├── pine_fmt.py
│   ├── pine_lint.py
│   ├── pine_run.py
│   ├── publish.py
│   ├── scaffold_project.py
│   ├── strategy_to_indicator.py
│   └── strip_comments.py
├── references/
│   ├── alerts-guide.md
│   ├── decisions.md
│   ├── design-system.md
│   ├── lint-rules.fa.md
│   ├── lint-rules.md
│   ├── mtf-guide.md
│   ├── performance-guide.md
│   ├── pine-v6-guide.md
│   ├── publishing-guide.md
│   ├── repo-structure.md
│   ├── strategy-guide.md
│   ├── style-guide.md
│   └── troubleshooting.md
├── references/snippets/
│   ├── glyphs.pine
│   ├── live_update.pine
│   ├── palette.pine
│   └── table_helpers.pine
├── assets/templates/
│   ├── CHANGELOG_template.md
│   ├── dashboard_block_template.pine
│   ├── indicator_template.pine
│   ├── strategy_template.pine
│   └── test_block_template.pine
├── tests/
│   ├── test_backup_private.py
│   ├── test_bump_version.py
│   ├── test_compile_error_corpus.py
│   ├── test_docs_consistency.py
│   ├── test_generate_release_bundle.py
│   ├── test_htf.py
│   ├── test_new_tooling.py
│   ├── test_pine_interp.py
│   ├── test_pine_lint.py
│   ├── test_project_quality.py
│   ├── test_scaffold_project.py
│   ├── test_sessions.py
│   ├── test_shared_engine.py
│   ├── test_skill_packaging.py
│   ├── test_snapshots.py
│   ├── test_strategy_to_indicator.py
│   ├── test_strip_comments.py
│   └── test_untested_rules.py
└── .github/workflows/ci.yml
```
<!-- END GENERATED: tree -->

> Both blocks above are generated by `scripts/build_index.py` and checked in CI. The
> tree they replaced was hand-maintained, and by the time anyone looked it was missing
> four scripts and four reference docs.

---

## 🛠️ The Tools

### **pine_lint.py** — Your Pre-Flight Checklist
Offline linting for v6 compliance and performance:

```bash
# Human-readable output
python3 scripts/pine_lint.py indicators/my_rsi_bands/src/my_rsi_bands.pine

# JSON for CI/CD integration
python3 scripts/pine_lint.py indicators/my_rsi_bands/src/my_rsi_bands.pine --json

# Strict mode: warnings also fail
python3 scripts/pine_lint.py indicators/my_rsi_bands/src/my_rsi_bands.pine --strict
python3 scripts/pine_lint.py FILE --profile dev      # errors only, non-fatal
python3 scripts/pine_lint.py FILE --profile publish  # everything, warnings fatal
python3 scripts/pine_lint.py FILE --watch            # re-lint on every save
python3 scripts/pine_lint.py FILE --format editor    # path:line:col, for editors
python3 scripts/pine_lint.py FILE --format github    # CI annotations on the diff

# List all 59 rules (rules marked [--fix] can be repaired automatically)
python3 scripts/pine_lint.py --list-rules

# Explain one rule in full
python3 scripts/pine_lint.py --explain PINE045

# Apply the mechanical fixes
python3 scripts/pine_lint.py FILE --fix --dry-run
python3 scripts/pine_lint.py FILE --fix
```

**What it catches:**
- ❌ Hard v6 compile errors (`when=`, `transp=`, missing switch defaults, etc.)
- ❌ Repainting traps (`and`/`or` lazy evaluation, missing `lookahead=`, etc.)
- ⚠️ Performance warnings (plot count, label/box/polyline limits)
- ⚠️ Style violations (naming, line length, missing titles)

### **scaffold_project.py** — Bootstrap New Projects
```bash
python3 scripts/scaffold_project.py --kind indicator --name my_indicator --title "My Indicator"
python3 scripts/scaffold_project.py --kind strategy --name my_strategy --title "My Strategy"
```

Generates a complete project folder with:
- Professional template (theme picker, dashboard, test block)
- `version.json` at v0.1.0
- Empty `CHANGELOG.md` ready to fill

### **bump_version.py** — Semantic Versioning Made Easy
```bash
python3 scripts/bump_version.py indicators/my_rsi_bands --bump patch --note "Fixed off-by-one"
python3 scripts/bump_version.py indicators/my_rsi_bands --bump minor --note "Added new input"
python3 scripts/bump_version.py indicators/my_rsi_bands --bump major --note "Changed plot behavior"
```

Updates `version.json`, moves `[Unreleased]` to a dated entry in `CHANGELOG.md`,
and creates an annotated git tag `<project>/vX.Y.Z` — namespaced per project,
because several share this repo. Supports `--dry-run`, `--json` and `--no-tag`.
Tagging failure is reported, never fatal: a bump that succeeded must not be
undone because git was unavailable.

### **generate_release_bundle.py** — One-Command Release
```bash
python3 scripts/generate_release_bundle.py indicators/my_rsi_bands
```

Outputs to `release/`:
- ✅ **`my_rsi_bands.pine`** — Final linted script, MPL 2.0 header, **comments stripped**
- ✅ **`PUBLISH_DESCRIPTION.md`** — Pre-filled TradingView publish template
- ✅ **`INPUTS.md`** — Generated table of every setting, grouped as the panel groups them
- ✅ **`RELEASE_SUMMARY.txt`** — Lint results, test-mode check, readiness verdict

The released `.pine` carries **no comments**. This repo writes a lot of prose into its scripts on purpose, and all of it is for whoever changes the code — not for the person pasting the script into TradingView, who would otherwise read several hundred lines of it first. The source keeps every word.

Two things survive, because they are not really comments: `//@version=N`, which is a compiler directive, and the licence and copyright lines. Pass `--keep-comments` for the annotated copy.

Stripping is verified rather than assumed: `tests/test_strip_comments.py` runs every real indicator through the interpreter twice, with comments and without, and compares every drawing, plot and alert. A `//` inside a string is not a comment, and a stripper that thinks otherwise turns a tooltip containing a URL into a compile error.


### **pine_fmt.py** — Formatter
```bash
python3 scripts/pine_fmt.py indicators/my_rsi_bands/src/my_rsi_bands.pine
python3 scripts/pine_fmt.py FILE --check    # exit 1 if it would change (CI)
python3 scripts/pine_fmt.py FILE --diff     # show the changes, write nothing
```

Trailing whitespace, leading tabs, space after commas, spaces around
multi-character operators, blank-line runs. It never touches block indentation —
in Pine that is structure, so re-indenting is re-structuring — and it only ever
*adds* a missing space, never removes one, because this repo aligns `=` into
columns and a collapsing formatter would destroy every one of them.

### **input_inventory.py** — The Settings Panel as a Table
```bash
python3 scripts/input_inventory.py indicators/my_rsi_bands
python3 scripts/input_inventory.py FILE --json
```

Every input with its type, default, range and tooltip, grouped the way the
settings panel groups them. Runs automatically as part of the release bundle
(`release/INPUTS.md`), and it is most of a TradingView publish description
written for you.

### **mutate_check.py** — Do the Tests Actually Work?
```bash
python3 scripts/mutate_check.py              # every rule (~8 min)
python3 scripts/mutate_check.py --only PINE045
```

Disables one lint rule at a time and re-runs the suite. A rule whose absence
changes nothing has no test that can detect it breaking. The first run found 16
of 59 rules in exactly that state.

### **strategy_to_indicator.py** — Alert-Only View of a Strategy
```bash
python3 scripts/strategy_to_indicator.py strategies/my_strategy
```

Rewrites the declaration, turns order calls into `alert()`s that keep their id
and direction, and comments out the risk guards. **It refuses** when the
strategy reads live position state, and names every blocking line — an indicator
has no position, and faking one would produce alerts that disagree with the
backtest they claim to mirror.

### **pine_run.py** — Actually Execute The Script
```bash
python3 scripts/pine_run.py FILE --bars 400
python3 scripts/pine_run.py FILE --csv data.csv --var swings --var boxesUsed
python3 scripts/pine_run.py FILE --set "Price Rows Per Swing=200"
python3 scripts/pine_run.py FILE --sweep "Price Rows Per Swing=30,60,120,240"
```

The 59 lint rules match **patterns**. This runs the **code** — bar by bar, with
real series history, `var` persistence, user functions, UDTs, arrays and
`if`/`for`/`while`/`switch` as expressions — and reports what came out.

It is the difference between "this looks like it compiles" and "this produced
484 boxes across 4 swings with the POC at 104.22". Because `input.*()` reads
from an override map instead of the source, `--sweep` runs the same file under
many settings without editing anything.

**Every run prints its approximations.** Offline there is no intrabar data, no
higher-timeframe series and no order execution, and a result depending on any
of those is not exact. Saying so beside the number is the only honest way to
show it.

What it does not do, stated because a partial interpreter that hides its edges
is worse than none: confirmed bars only (no realtime ticks, so tick-order bugs
belong to the linter), no `request.*` data, and an unimplemented builtin
**raises** instead of returning `na` — a value invented there would travel
silently into every result downstream.

### **doctor.py** — One Command, One Verdict
```bash
python3 scripts/doctor.py --fast     # everything except the 8-minute mutation run
python3 scripts/doctor.py --json
```

Ten checks, one table, one answer. Running them individually means occasionally
forgetting one, and the one you forget is the one that would have caught
something.

A check that cannot run in the current checkout is reported as **skipped**, by
name, and never counted as a pass — the whole point is that a green line for a
check that never executed is worse than a red one.

### **build_pine.py** — Write Parts, Ship One File
```bash
python3 scripts/build_pine.py PROJECT --split    # one-time, at the section banners
python3 scripts/build_pine.py PROJECT            # build
python3 scripts/build_pine.py PROJECT --check    # CI: is the output current?
```

Pine has no modules, so a growing script has nowhere to go but down. This repo's
largest file passed 1800 lines and produced a compile error that was purely
about ORDER — a declaration sitting below the function that read it — which
nothing in a file that size makes visible.

Order comes from `src/parts.json`, not from filename prefixes, because Pine
resolves identifiers in textual order and that ordering is a real design
decision rather than a filing convention.

### **complexity.py** — Growth As A Decision, Not A Drift
```bash
python3 scripts/complexity.py
python3 scripts/complexity.py --check              # CI
python3 scripts/complexity.py --update-baseline
```

Lines, function count, longest function, nesting depth, input count.

Two kinds of limit, deliberately. The **advisory** thresholds are repo-wide and
never fail a run. What fails is a project exceeding the limit **it declared** in
its own `budget.json`. A repo-wide hard threshold applied to existing code
either fails from day one or is set so loose it never fires; a declared limit is
a ratchet, and raising one is a visible decision in a diff.

### **check_budget.py** — Declared Resource Limits
```bash
python3 scripts/check_budget.py
python3 scripts/check_budget.py PROJECT --init
```

Boxes, lines, labels, plot counts and `request.*()` calls against the numbers
each project declared. TradingView's own limits are silent — over 500 boxes the
oldest simply stop drawing — and the point here is the *declared* number: an
intentional "this should use at most 3 requests" catches a fourth long before
the platform's ceiling would.

### **check_inputs_compat.py** — The Break Users See And You Don't
```bash
python3 scripts/check_inputs_compat.py PROJECT
```

TradingView matches a saved chart setting to an input by its **title**. Rename
one and every existing user silently loses that setting; remove one and the same
happens. This is the only breaking change in a Pine script the author cannot see
from their own chart, because their own settings are already saved.

Compares the current inputs against the last published `INPUTS.md` and names
what broke. Wired into the release bundle as a warning, not a blocker — renaming
an input is legitimate; doing it *without noticing* is not.

### **publish.py** — Straight To The Pine Editor
```bash
python3 scripts/publish.py PROJECT           # release .pine -> clipboard
python3 scripts/publish.py PROJECT --notes   # release notes, plain text
```

Copies the **release** file, not `src/` — the one that went through the gate.
`--notes` flattens the changelog entry into the plain text TradingView's
update-notes box actually accepts, instead of Markdown that renders as
punctuation.

### **build_fa_reference.py** — Persian Rule Reference
```bash
python3 scripts/build_fa_reference.py
python3 scripts/build_fa_reference.py --check    # CI
```

Generates [`references/lint-rules.fa.md`](references/lint-rules.fa.md) from the
rule catalog, so codes and severities can never drift from the code. A rule with
no translation renders with its English summary **and is listed as
untranslated**, so the gap is visible rather than silently missing.

### **check_library_sync.py** — The Copies Have Not Drifted
```bash
python3 scripts/check_library_sync.py
python3 scripts/check_library_sync.py --json
```

TradingView's `import` only works against a library that has been **published**
to their servers, so until `libraries/pine_toolkit` is, every script carries its
own copy of `formatVolume()` and friends. This compares each `export`ed function
against every same-named copy and reports the ones whose body differs.

Its first run found **6 of 7 copies drifted**, including one indicator
formatting the same volume with a different number of decimals than the other
two. Nobody chose that. A copy that is deliberately specialised opts out with a
`// library-sync-exempt: <reason>` comment; two of them legitimately did.

### **build_index.py** — Project Registry
```bash
python3 scripts/build_index.py            # regenerate the marked regions
python3 scripts/build_index.py --check    # exit 1 if stale (CI)
```

Regenerates the project table and file tree in this README from the repo itself.

### **lint_all.py / install_hooks.py / new_rule.py**
```bash
python3 scripts/lint_all.py               # lint every source .pine at once
python3 scripts/install_hooks.py          # pre-commit lint hook
python3 scripts/new_rule.py --next        # scaffold a new lint rule
```

---

## 📚 Reference Guides

Every script benefits from these docs; required reading before shipping:

| Guide | Purpose |
|-------|---------|
| **[mtf-guide.md](references/mtf-guide.md)** | Multi-timeframe: the three `lookahead` combinations and which is the bug, `security_lower_tf`, gaps, the 40-call budget, repaint vs lookahead |
| **[alerts-guide.md](references/alerts-guide.md)** | `alertcondition` vs `alert()`, frequency, placeholders, webhook JSON, and the security rules for alert payloads |
| **[troubleshooting.md](references/troubleshooting.md)** | Symptom-first: every failure this repo hit, its cause, and the rule that now catches it |
| **[decisions.md](references/decisions.md)** | Decision record — what was decided, why, and what would change our mind |
| **[pine-v6-guide.md](references/pine-v6-guide.md)** | v5→v6 breaking changes, platform limits, dynamic requests, repainting traps, `var`/`varip` semantics |
| **[style-guide.md](references/style-guide.md)** | Official naming conventions (camelCase/SNAKE_CASE), section order, spacing, line wrapping |
| **[lint-rules.md](references/lint-rules.md)** | Full catalog of 59 lint rules (codes PINE001–PINE060; PINE024 unassigned) with examples and rationale |
| **[performance-guide.md](references/performance-guide.md)** | Keeping a script fast AND live: work tiering, memoization, buffer reuse, drawing updates, var vs varip |
| **[strategy-guide.md](references/strategy-guide.md)** | Building strategies: signal design, position sizing math, the four risk modules, filters, overfitting, walk-forward |
| **[design-system.md](references/design-system.md)** | Theming, gradients, multi-color palettes, watermarks, dashboard patterns |
| **[publishing-guide.md](references/publishing-guide.md)** | TradingView House Rules, description format, backtest realism, 15-min public edit window |
| **[repo-structure.md](references/repo-structure.md)** | Folder layout, `version.json`, CHANGELOG format, optional pre-commit hook |

---

## 💡 Example: Build an RSI Indicator from Start to Finish

```bash
# 1. Scaffold
python3 scripts/scaffold_project.py --kind indicator --name rsi_custom --title "Custom RSI"

# 2. Edit indicators/rsi_custom/src/rsi_custom.pine with your logic

# 3. Add test assertions to the Test Mode block

# 4. Lint
python3 scripts/pine_lint.py indicators/rsi_custom/src/rsi_custom.pine
# Output: ✓ No errors

# 5. Bump version
python3 scripts/bump_version.py indicators/rsi_custom --bump minor --note "Initial release with bands"

# 6. Generate release
python3 scripts/generate_release_bundle.py indicators/rsi_custom

# 7. Check release/
# - rsi_custom.pine           (ready to paste)
# - PUBLISH_DESCRIPTION.md    (fill in the [bracketed] placeholders)
# - RELEASE_SUMMARY.txt       (confirms READY status)

# 8. Publish to TradingView
# Copy rsi_custom.pine → Pine Editor → Publish Script (paste description)
```

---

## 🛡️ Example: Build a Strategy with Real Risk Management

```bash
# 1. Scaffold — the template arrives with all four risk modules already wired
python3 scripts/scaffold_project.py --kind strategy --name breakout_atr --out ./strategies --title "ATR Breakout"

# 2. Replace ONLY the signal block in src/breakout_atr.pine:
#      bool longSignal  = ta.crossover(fastMa, slowMa)
#      bool shortSignal = ta.crossunder(fastMa, slowMa)
#    Everything else — sizing, stops, breakeven, trailing, partials, filters —
#    is generic and stays as-is.

# 3. Lint in strict mode (warnings fail too)
python3 scripts/pine_lint.py strategies/breakout_atr/src/breakout_atr.pine --strict

# 4. Backtest on TradingView, then check the dashboard's Realism row:
#    100+ POSITIONS taken (not closed records — partials double that number)
#    and profit factor above 1.

# 5. Release — the bundle blocks on lookahead bias, synthetic chart types,
#    and zero-cost backtests, and pre-fills the disclosure section
python3 scripts/generate_release_bundle.py strategies/breakout_atr
```

Before trusting any equity curve, read
**[strategy-guide.md](references/strategy-guide.md)** §7 — a good-looking backtest
is the default outcome, not evidence. The fastest sanity check: move your stop
multiple ±25% and see whether the result degrades gracefully or collapses.

---

## 🎯 Key Features

| | |
|---|---|
| **59 lint rules** | PINE001–PINE060 (PINE024 vacant), fact-checked against TradingView's docs; 7 auto-fixable |
| **Offline execution** | `pine_run.py` runs a script bar by bar over real or synthetic OHLCV, with series history and `var` semantics |
| **Parameter sweeps** | One file, many settings — `input.*()` reads from an override map |
| **Symbol table** | Undeclared `:=` targets, unused and write-only variables |
| **Cost analysis** | Loop nests costed at their inputs' `maxval`; drawings made in loops checked against `max_*_count` |
| **Formatter** | `--check` gate in CI; never re-indents, never collapses alignment columns |
| **230 tests** | stdlib `unittest`, zero dependencies |
| **Mutation-checked** | 59/59 rules verified to have a test that fails when the rule is disabled |
| **Strategy risk modules** | Risk-% sizing, ATR stops, breakeven, trailing, partials, filters, `strategy.risk.*` account guards |
| **Backtest realism gate** | Blocks lookahead bias, synthetic chart types, zero-cost backtests |
| **In-script testing** | Assertion counter inside the Pine file; no external runner |
| **Release bundles** | Lint → version → changelog → git tag → publish description → inputs table |
| **Generated docs** | Project registry, file tree and Persian rule reference built from the repo, `--check`ed in CI |
| **One-command verdict** | `doctor.py` runs all ten checks; a skipped check is named, never counted as a pass |
| **Part-file builds** | Write `src/parts/*.pine`, ship one file; order declared in a manifest, not in filenames |
| **Declared limits** | Per-project resource and complexity budgets — a ratchet, so growth is a decision |
| **Input compatibility** | Catches the renames that silently reset every existing user's settings |
| **12 reference guides** | v6, style, lint catalog, performance, strategy, design, publishing, repo structure, MTF, alerts, troubleshooting, decisions |
| **Shared library** | `libraries/pine_toolkit` — pure helpers as a real Pine `library()`, with inlined copies checked for drift |
| **Snapshot tests** | Publish description, inputs table and release summary compared against stored goldens |
| **Offline** | No compile-API dependency; everything runs on your machine |

---

## 🧪 Development & CI

The Python tooling has its own test suite (stdlib `unittest`, no dependencies):

```bash
python -m unittest discover -s tests -t . -v     # 230 tests
python scripts/lint_all.py                       # every source .pine, strict
python scripts/pine_fmt.py FILE --check          # formatting gate
python scripts/build_index.py --check            # generated docs are current
python scripts/check_library_sync.py             # inlined library copies match
python scripts/pine_run.py FILE --bars 300       # execute it, offline
python scripts/doctor.py --fast                  # all of the above, one verdict
python scripts/mutate_check.py                   # ~8 min; see below
```

GitHub Actions ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs four
jobs: the test suite, the Pine lint + format sweep, the generated-docs check,
and — on pushes to `main` only — the mutation run.

**Why a mutation job.** A green suite proves the tests pass. It does not prove
they would fail if the thing they test broke, and a test that cannot fail is
worth nothing. `mutate_check.py` disables one lint rule at a time and re-runs
the suite; a rule whose absence changes nothing is one the next refactor can
delete silently. The first run found **16 of 59 rules in exactly that state** —
nearly a third of the catalog, invisible while everything reported OK.

**Adding a lint rule.** `scripts/new_rule.py` scaffolds the catalog entry, the
check stub, the call site and the docs section. The consistency tests then fail
until the rule is documented and the counts line up, which is the point.

---

## 🤔 Why Pine Script Skill?

**Without this skill:**
- Write indicator → paste into TradingView → discover v6 error → debug → repeat
- Maintain 3+ indicators manually → inconsistent naming, no changelogs, versioning chaos
- Publish to TradingView → no release notes, no version tracking, hard to maintain

**With Pine Script Skill:**
- Write indicator → lint and format locally, catching most errors *before* TradingView
- Scaffold → Write → Lint → Test → Version → Tag → Release → Publish, repeatably
- Maintain 10+ indicators with independent versions, changelogs, git tags and release history
- When something *does* slip through, it becomes a fixture and a rule, so it cannot come back
- **Spend more time trading, less time wrestling with process**

---

## 📖 Full Documentation

See [SKILL.md](SKILL.md) for complete details on:
- When to use which part of the toolchain
- Detailed scaffold & templating workflow
- In-script testing patterns
- Git integration & pre-commit hooks
- Advanced linting configuration

Start with [troubleshooting.md](references/troubleshooting.md) when something is
already wrong — it is indexed by symptom, and every row in it happened here.

---

## 🔧 Requirements

- **Python 3.8+** — for scripts (no external dependencies!)
- **Pine Script v6** knowledge — [TradingView docs](https://www.tradingview.com/pine-script-docs/)
- **TradingView Account** — free or pro (for publishing)
- **Git** (optional) — for version control

---

## 📝 License

All scripts and templates are licensed under the **Mozilla Public License 2.0** (MPL 2.0).  
Generated `.pine` files include the MPL 2.0 header automatically.

---

## 🤝 Contributing

Found a bug in a lint rule? Spot a v6 edge case we missed? Spotted a typo in the guides?

Please [open an issue](https://github.com/MoDarK-MK/PineScript-Skill/issues) or submit a PR. This is a working tool for traders building real indicators—your feedback matters.

---

## 🚀 Get Started Now

```bash
git clone https://github.com/MoDarK-MK/PineScript-Skill.git
cd PineScript-Skill
python3 scripts/scaffold_project.py --kind indicator --name my_first --title "My First Indicator"
# Start editing indicators/my_first/src/my_first.pine
```

**Questions?** Check [SKILL.md](SKILL.md) or the reference guides in `references/`.

---

**Happy trading.** 📈
