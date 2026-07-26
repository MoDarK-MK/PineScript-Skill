#!/usr/bin/env python3
"""
generate_release_bundle.py - Assemble a release-ready bundle for one
indicator/strategy project: lints the source, sanity-checks it's actually
safe to publish (test mode off by default, license header present), drafts a
publish-description scaffold from the changelog, and writes everything to an
output folder ready to copy-paste into TradingView's Pine Editor and
"Publish script" flow.

Usage:
    python3 generate_release_bundle.py <project_dir> [--out <release_dir>] [--strict]

<project_dir> must contain (the standard layout from references/repo-structure.md):
    src/<name>.pine
    version.json
    CHANGELOG.md

Output (written to <release_dir>, default <project_dir>/release/):
    <name>.pine              - final source, license header added if missing
    PUBLISH_DESCRIPTION.md   - drafted TradingView publish-description scaffold
    RELEASE_SUMMARY.txt      - what this script checked and found

Exit code 0 only if the lint is clean (errors; warnings unless --strict) AND
no test-mode input was left defaulting to true.
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import pine_lint  # noqa: E402  (reuse the same linter, don't reimplement checks)

LICENSE_HEADER = (
    "// This source code is subject to the terms of the Mozilla Public License 2.0 "
    "at https://mozilla.org/MPL/2.0/\n"
)


def find_source_file(project_dir, name):
    src_path = project_dir / "src" / f"{name}.pine"
    if src_path.exists():
        return src_path
    src_dir = project_dir / "src"
    candidates = list(src_dir.glob("*.pine")) if src_dir.exists() else []
    if len(candidates) == 1:
        return candidates[0]
    return None


def check_test_mode_default(text):
    """Returns a list of human-readable warnings for any test-mode-looking
    input that defaults to true — that would ship debug labels/dashboards
    turned on for every user by default."""
    warnings = []
    for m in re.finditer(r'(\w*[Tt]est\w*)\s*=\s*input\.bool\(\s*true\b', text):
        warnings.append(
            f"'{m.group(1)}' looks like a test-mode toggle defaulting to TRUE — flip it to "
            f"false before publishing, or debug labels/dashboards will show for every user."
        )
    return warnings


def ensure_license_header(text):
    if "License" in text.split("\n", 1)[0] or "license" in text[:300].lower():
        return text, False
    return LICENSE_HEADER + text, True


SYNTHETIC_TICKERS = (
    "ticker.heikinashi(", "ticker.renko(", "ticker.linebreak(",
    "ticker.kagi(", "ticker.pointfigure(", "ticker.range(",
)


def parse_declaration_args(text):
    """Returns {param: value_expression} for the strategy()/indicator() call, or
    {} if it can't be parsed. Reuses pine_lint's statement grouping so a
    multi-line declaration is handled correctly."""
    statements = pine_lint.build_logical_statements(text.splitlines())
    decl = pine_lint.find_declaration_statement(statements)
    if decl is None:
        return {}
    flat = pine_lint.strip_comments_only_multi(decl["raw_nc"])
    for func in ("strategy(", "indicator("):
        arg_text = pine_lint.call_arg_text(flat, func)
        if arg_text is not None:
            break
    else:
        return {}
    parsed = {}
    for arg in pine_lint.split_top_level_args(arg_text):
        m = re.match(r'^([a-zA-Z_]\w*)\s*=(?!=)\s*(.*)$', arg, re.DOTALL)
        if m:
            parsed[m.group(1)] = m.group(2).strip()
    return parsed


def check_strategy_realism(text, lint_result):
    """Strategy-only publish gate. Returns (blocking, advisory) message lists.

    Blocking items are TradingView rules violations or backtests that can't be
    published as-is; advisory items are judgement calls worth seeing.
    """
    blocking = []
    advisory = []
    decl = parse_declaration_args(text)

    # 1. Lookahead bias: lookahead_on is only legitimate with an offset expression.
    statements = pine_lint.build_logical_statements(text.splitlines())
    for stmt in statements:
        if "barmerge.lookahead_on" in stmt["stripped"] and "[1]" not in stmt["stripped"]:
            blocking.append(
                f"line {stmt['start']}: request.*() uses barmerge.lookahead_on without an "
                f"offset expression ([1]) — this reads data that wasn't available yet. "
                f"TradingView's House Rules prohibit publishing scripts with lookahead bias.")

    # 2. Synthetic-price chart types in a script that trades.
    for func in SYNTHETIC_TICKERS:
        if func in text:
            blocking.append(
                f"{func[:-1]}() is used — non-standard chart types show synthetic prices, "
                f"and House Rules prohibit them in a script that trades, alerts, or signals.")

    # 3. A zero-cost backtest.
    commission = decl.get("commission_value")
    slippage = decl.get("slippage")
    zero_commission = commission is None or commission.strip() in ("0", "0.0")
    zero_slippage = slippage is None or slippage.strip() == "0"
    if zero_commission and zero_slippage:
        blocking.append(
            "the declaration sets neither a nonzero commission_value nor a nonzero slippage "
            "— a frictionless backtest overstates every result and isn't publishable.")

    # 4. Name the strategy lint errors explicitly so the reason is visible here.
    fatal_codes = {"PINE029", "PINE033", "PINE034"}
    for f in lint_result.findings:
        if f.code in fatal_codes:
            blocking.append(f"line {f.line}: [{f.code}] {f.msg}")

    # ————— Advisory
    capital = decl.get("initial_capital")
    if capital is not None:
        try:
            value = float(capital)
            if not (100 <= value <= 1_000_000):
                advisory.append(
                    f"initial_capital={capital} is outside the 100-1,000,000 range that reads as "
                    f"'a realistic amount for an average trader'.")
        except ValueError:
            pass
    qty_type = decl.get("default_qty_type", "")
    qty_value = decl.get("default_qty_value")
    if "percent_of_equity" in qty_type and qty_value is not None:
        try:
            if float(qty_value) > 10:
                advisory.append(
                    f"default_qty_value={qty_value}% of equity per trade exceeds the ~10% "
                    f"sustainable-sizing rule of thumb.")
        except ValueError:
            pass
    for m in re.finditer(r'input\.float\(\s*([\d.]+)\s*,\s*"([^"]*[Rr]isk[^"]*)"', text):
        try:
            if float(m.group(1)) > 10:
                advisory.append(
                    f'risk input "{m.group(2)}" defaults to {m.group(1)} — above the ~10% '
                    f"per-trade rule of thumb.")
        except ValueError:
            pass
    if re.search(r'calc_on_every_tick\s*=\s*true', text):
        advisory.append(
            "calc_on_every_tick=true makes historical and realtime results diverge — the "
            "historical run only ever sees closed bars.")
    if not any(f in text for f in ("strategy.exit(", "strategy.close(", "strategy.close_all(")):
        advisory.append(
            "no strategy.exit()/close()/close_all() found — positions are only closed by an "
            "opposite entry, so no trade has a defined risk.")
    return blocking, advisory


def backtest_disclosure_lines(decl):
    """Pre-fills the disclosure section from the real declaration values, falling
    back to the bracketed prompt when a value can't be parsed."""
    if not decl:
        return [
            "[State initial capital, commission, slippage, and position sizing used in the "
            "published backtest, and confirm these are the script's actual defaults, not "
            "fine-tuned for this one chart.]",
        ]
    lines = []
    capital = decl.get("initial_capital")
    currency = decl.get("currency", "").replace("currency.", "")
    if capital:
        lines.append(f"- Initial capital: {capital}{(' ' + currency) if currency else ''}")
    commission = decl.get("commission_value")
    commission_type = decl.get("commission_type", "").replace("strategy.commission.", "")
    if commission:
        unit = "%" if commission_type == "percent" else f" ({commission_type})" if commission_type else ""
        lines.append(f"- Commission: {commission}{unit} per trade")
    if decl.get("slippage"):
        lines.append(f"- Slippage: {decl['slippage']} tick(s)")
    qty_type = decl.get("default_qty_type", "").replace("strategy.", "")
    if decl.get("default_qty_value"):
        lines.append(f"- Default position sizing: {decl['default_qty_value']} ({qty_type})")
    if decl.get("margin_long") or decl.get("margin_short"):
        lines.append(f"- Margin: long {decl.get('margin_long', '?')}%, "
                     f"short {decl.get('margin_short', '?')}%")
    if decl.get("pyramiding"):
        lines.append(f"- Pyramiding: {decl['pyramiding']}")
    lines.append("")
    lines.append("[Confirm these are the script's actual defaults, and state the trade count "
                 "from your published chart — aim for 100+. If the script takes partial exits, "
                 "report positions taken, not the Strategy Tester's closed-trade count. "
                 "See references/publishing-guide.md.]")
    return lines


def build_publish_description(name, version_info, changelog_text, is_strategy, decl=None):
    version = version_info.get("version", "0.0.0")
    lines = [
        f"# Publish description draft for {name} v{version}",
        "",
        "> Fill in the bracketed sections below with specifics about this script's actual "
        "logic, then paste everything below the '---' into TradingView's description field. "
        "See references/publishing-guide.md for the full rules this structure follows.",
        "",
        "---",
        "",
        "## Purpose",
        "[What does this script show or do, in 1-2 sentences?]",
        "",
        "## How it works",
        "[Explain the calculation/logic in plain language — this is what makes a script "
        "'original' rather than a re-skin of a built-in, and TradingView moderators check for it.]",
        "",
        "## How to use it",
        "[Settings worth knowing, what a signal means, how to read the dashboard if this "
        "script has one.]",
        "",
        "## Originality",
        "[Why this isn't just a copy of an existing public script, if relevant.]",
    ]
    if is_strategy:
        lines += ["", "## Backtest settings disclosure (required for strategies)", ""]
        lines += backtest_disclosure_lines(decl or {})
    lines += [
        "",
        "## Changelog",
        "```",
        changelog_text.strip(),
        "```",
    ]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Assemble a release bundle for one Pine project.")
    parser.add_argument("project_dir", help="Path to the project folder (contains src/, version.json, CHANGELOG.md)")
    parser.add_argument("--out", default=None, help="Output directory (default: <project_dir>/release)")
    parser.add_argument("--strict", action="store_true", help="Treat lint warnings as blocking too")
    args = parser.parse_args()

    project_dir = Path(args.project_dir)
    if not project_dir.exists():
        print(f"error: {project_dir} does not exist.", file=sys.stderr)
        return 1

    version_path = project_dir / "version.json"
    changelog_path = project_dir / "CHANGELOG.md"
    if not version_path.exists():
        print(f"error: {version_path} not found — is this a scaffolded project folder?", file=sys.stderr)
        return 1

    version_info = json.loads(version_path.read_text(encoding="utf-8"))
    name = version_info.get("name", project_dir.name)
    is_strategy = version_info.get("kind") == "strategy"

    src_path = find_source_file(project_dir, name)
    if src_path is None:
        print(f"error: couldn't find a single .pine file under {project_dir / 'src'}.", file=sys.stderr)
        return 1

    out_dir = Path(args.out) if args.out else project_dir / "release"
    out_dir.mkdir(parents=True, exist_ok=True)

    text = src_path.read_text(encoding="utf-8")

    cfg = pine_lint.load_config(str(project_dir / ".pine-lint.json"))
    lint_result = pine_lint.lint_file(str(src_path), cfg)
    lint_ok = lint_result.ok(strict=args.strict)

    test_mode_warnings = check_test_mode_default(text)
    text_with_license, license_added = ensure_license_header(text)

    strategy_blocking, strategy_advisory = ([], [])
    declaration = {}
    if is_strategy:
        declaration = parse_declaration_args(text)
        strategy_blocking, strategy_advisory = check_strategy_realism(text, lint_result)

    final_pine_path = out_dir / f"{name}.pine"
    final_pine_path.write_text(text_with_license, encoding="utf-8")

    changelog_text = changelog_path.read_text(encoding="utf-8") if changelog_path.exists() else "(no CHANGELOG.md found)"
    desc = build_publish_description(name, version_info, changelog_text, is_strategy, declaration)
    (out_dir / "PUBLISH_DESCRIPTION.md").write_text(desc, encoding="utf-8")

    summary_lines = [
        f"Release bundle for {name} v{version_info.get('version', '?')}",
        f"Generated {datetime.date.today().isoformat()}",
        "",
        f"Lint result: {len(lint_result.by_severity('error'))} error(s), "
        f"{len(lint_result.by_severity('warning'))} warning(s), "
        f"{len(lint_result.by_severity('info'))} note(s).",
    ]
    for f in sorted(lint_result.findings, key=lambda x: (x.line, x.code)):
        summary_lines.append(f"  {src_path.name}:{f.line}: {f.severity.upper()} [{f.code}]: {f.msg}")
    summary_lines.append("")
    if is_strategy:
        if strategy_blocking or strategy_advisory:
            summary_lines.append("Strategy realism checks:")
            for w in strategy_blocking:
                summary_lines.append(f"  BLOCKING: {w}")
            for w in strategy_advisory:
                summary_lines.append(f"  NOTE: {w}")
        else:
            summary_lines.append("Strategy realism checks: none found. OK.")
        summary_lines.append("")
    if test_mode_warnings:
        summary_lines.append("Test-mode defaults:")
        for w in test_mode_warnings:
            summary_lines.append(f"  WARNING: {w}")
    else:
        summary_lines.append("Test-mode defaults: none found defaulting to true. OK.")
    summary_lines.append("")
    summary_lines.append(f"License header: {'added (was missing)' if license_added else 'already present'}.")
    summary_lines.append("")
    ready = lint_ok and not test_mode_warnings and not strategy_blocking
    if args.strict and strategy_advisory:
        ready = False
    summary_lines.append("READY TO PUBLISH." if ready else "NOT READY — resolve the items above first.")
    (out_dir / "RELEASE_SUMMARY.txt").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(f"Release bundle written to {out_dir}")
    print(f"  - {final_pine_path.name}")
    print("  - PUBLISH_DESCRIPTION.md")
    print("  - RELEASE_SUMMARY.txt")
    print()
    print("\n".join(summary_lines))

    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
