# 🎯 Pine Script Skill
> **Production-Grade TradingView Pine Script Indicators & Strategies**

[![License: MPL 2.0](https://img.shields.io/badge/License-MPL%202.0-brightgreen.svg)](https://opensource.org/licenses/MPL-2.0)
[![Pine Script v6](https://img.shields.io/badge/Pine%20Script-v6-1f51b6.svg)](https://www.tradingview.com/)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-3776ab.svg)](https://www.python.org/)

Transform your TradingView Pine Script ideas into **production-ready indicators and strategies** with professional tooling, automated linting, structured versioning, and release pipelines—all without leaving your editor.

## ✨ What Makes This Different

Most Pine Script traders treat each indicator as a one-off script. Pine Script Skill treats them like **real projects**:

- 🔍 **27-Rule Linter** — Catches v6 compile errors, performance traps, and style issues *before* you paste into TradingView
- 📋 **Professional Templates** — Scaffold new indicators/strategies with theme-aware dashboards, test blocks, and best-practice structure
- ✅ **In-Script Testing** — Write assertions directly in your code; results show in a test-mode table
- 📦 **Automated Releases** — Generate lint reports, version bumps, changelogs, and publish descriptions with one command
- 🎨 **Design System** — Gradients, multi-color palettes, watermarks, and professional styling guidelines
- 📚 **Complete Reference Docs** — v6 migration guide, style guide, publish best practices, lint rule catalog

Perfect for traders who want **repeatable workflows** across multiple indicators, not just quick one-offs.

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

### 4. Lint Before Publishing
```bash
python3 scripts/pine_lint.py indicators/my_rsi_bands/src/my_rsi_bands.pine
```
Catches v6 errors, repainting traps, performance issues, and style violations—**offline, no TradingView compiler needed**.

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
- Release checklist summary

### 7. Publish to TradingView
Paste the `.pine` file into the Pine Editor, use the generated description, publish. Done.

---

## 📁 Project Structure

```
PineScript-Skill/
├── indicators/
│   └── <name>/
│       ├── src/<name>.pine          # Your indicator code
│       ├── version.json             # Semantic versioning
│       └── CHANGELOG.md             # Changelog (Keep a Changelog format)
├── strategies/
│   └── <name>/
│       ├── src/<name>.pine          # Strategy with risk management
│       ├── version.json
│       └── CHANGELOG.md
├── assets/templates/
│   ├── indicator_template.pine      # Start here for new indicators
│   ├── strategy_template.pine       # Start here for new strategies
│   ├── dashboard_block_template.pine # Dashboard component patterns
│   └── test_block_template.pine     # Testing patterns
├── scripts/
│   ├── pine_lint.py                 # 27-rule offline linter
│   ├── scaffold_project.py          # Bootstrap new indicators/strategies
│   ├── bump_version.py              # Semantic versioning + changelog
│   └── generate_release_bundle.py   # Auto-generate release files
├── references/
│   ├── pine-v6-guide.md             # v5→v6 breaking changes & platform limits
│   ├── style-guide.md               # Naming, spacing, section order
│   ├── lint-rules.md                # Full catalog of 27 lint rules (PINE001-028)
│   ├── design-system.md             # Theming, gradients, dashboards
│   ├── publishing-guide.md          # TradingView House Rules condensed
│   └── repo-structure.md            # Folder layout, versioning, changelog format
└── SKILL.md                         # Full documentation
```

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

# List all 27 rules
python3 scripts/pine_lint.py --list-rules
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

Updates `version.json` and moves `[Unreleased]` to a dated entry in `CHANGELOG.md`.

### **generate_release_bundle.py** — One-Command Release
```bash
python3 scripts/generate_release_bundle.py indicators/my_rsi_bands
```

Outputs to `release/`:
- ✅ **`my_rsi_bands.pine`** — Final linted source with MPL 2.0 header
- ✅ **`PUBLISH_DESCRIPTION.md`** — Pre-filled TradingView publish template
- ✅ **`RELEASE_SUMMARY.txt`** — Lint results, test-mode check, readiness verdict

---

## 📚 Reference Guides

Every script benefits from these docs; required reading before shipping:

| Guide | Purpose |
|-------|---------|
| **[pine-v6-guide.md](references/pine-v6-guide.md)** | v5→v6 breaking changes, platform limits, dynamic requests, repainting traps, `var`/`varip` semantics |
| **[style-guide.md](references/style-guide.md)** | Official naming conventions (camelCase/SNAKE_CASE), section order, spacing, line wrapping |
| **[lint-rules.md](references/lint-rules.md)** | Full catalog of 27 lint rules (PINE001-028) with examples and rationale |
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

## 🎯 Key Features

✅ **27-Rule Linter** — Fact-checked against TradingView docs (v6 as of mid-2026)  
✅ **In-Script Testing** — Assertion counter; no external test runner  
✅ **Theme System** — Dark/light mode aware; professional gradients & dashboards  
✅ **Semantic Versioning** — MAJOR/MINOR/PATCH with automatic changelog  
✅ **Release Bundles** — Lint → version → changelog → publish description → ready to go  
✅ **No Compile API Dependency** — Everything runs offline on your machine  
✅ **Professional Templates** — Indicators, strategies, dashboards, test patterns  
✅ **Comprehensive Docs** — v6 guide, style guide, design system, publish rules  
✅ **Git-Ready** — Structure supports multi-indicator repos and version control  

---

## 🤔 Why Pine Script Skill?

**Without this skill:**
- Write indicator → paste into TradingView → discover v6 error → debug → repeat
- Maintain 3+ indicators manually → inconsistent naming, no changelogs, versioning chaos
- Publish to TradingView → no release notes, no version tracking, hard to maintain

**With Pine Script Skill:**
- Write indicator → lint locally (catches errors *before* TradingView)
- Scaffold → Write → Lint → Test → Version → Release → Publish in one repeatable workflow
- Maintain 10+ indicators professionally with independent versions, changelogs, and release history
- **Spend more time trading, less time wrestling with process**

---

## 📖 Full Documentation

See [SKILL.md](SKILL.md) for complete details on:
- When to use which part of the toolchain
- Detailed scaffold & templating workflow
- In-script testing patterns
- Git integration & pre-commit hooks
- Advanced linting configuration

---

## 🔧 Requirements

- **Python 3.8+** — for scripts (no external dependencies!)
- **Pine Script v6** knowledge — [TradingView docs](https://www.tradingview.com/pine-script-docs/en/v5/)
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
