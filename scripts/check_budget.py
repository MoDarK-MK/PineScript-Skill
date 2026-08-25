#!/usr/bin/env python3
"""
check_budget.py - Hold each project to a declared resource budget.

TradingView's limits are silent. Go over 500 boxes and the oldest ones simply
stop drawing; go over 64 plot counts or 40 requests and the script fails to
load, but only once it is already pasted. The numbers that keep a script under
those limits currently live in comments spread through the source, where they
are neither checked nor visible.

A `budget.json` next to `version.json` states them in one place, and this
compares the source against it. The point is not the ceiling — TradingView's
ceiling never moves — it is the DECLARED number: an intentional "this script
should use at most 3 requests" catches a fourth one appearing, long before the
platform's own limit would.

Missing budget.json means the project has not made those decisions yet, which is
reported rather than passed.

Usage:
    python3 scripts/check_budget.py                  # every project
    python3 scripts/check_budget.py PROJECT
    python3 scripts/check_budget.py PROJECT --init   # write a budget from current usage
    python3 scripts/check_budget.py --json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pine_lint

ROOT = Path(__file__).resolve().parent.parent
SEARCH_DIRS = ("indicators", "strategies", "libraries")

# TradingView's own ceilings. A declared budget may sit below these; it may
# never sit above them, and --init clamps rather than proposing the impossible.
PLATFORM_MAX = {
    "boxes": 500, "lines": 500, "labels": 500, "polylines": 100,
    "tables": 9, "plot_counts": 64, "requests": 40,
}

DECL_PARAMS = {
    "boxes": "max_boxes_count",
    "lines": "max_lines_count",
    "labels": "max_labels_count",
    "polylines": "max_polylines_count",
}


def measure(source):
    text = source.read_text(encoding="utf-8")
    lines = text.splitlines()
    statements = pine_lint.build_logical_statements(lines)
    decl = pine_lint.find_declaration_statement(statements)
    decl_text = decl["stripped"] if decl else ""

    used = {}
    for key, param in DECL_PARAMS.items():
        value = None
        if param in decl_text:
            args = pine_lint.split_top_level_args(
                pine_lint.call_arg_text(decl_text, "indicator(")
                or pine_lint.call_arg_text(decl_text, "strategy(") or "")
            raw = pine_lint.named_arg(args, param)
            if raw and raw.strip().isdigit():
                value = int(raw.strip())
        # Undeclared means TradingView's default of 50, not "unlimited".
        used[key] = value if value is not None else (50 if key != "polylines" else 50)

    # Real calls only. A substring count read `box.set_bgcolor(` as a bgcolor()
    # plot and `array.fill(` as a fill(), against a hard limit of 64.
    used["plot_counts"] = pine_lint.count_plot_calls(text)
    used["tables"] = text.count("table.new(")
    used["requests"] = sum(text.count(f) for f in
                           ("request.security(", "request.security_lower_tf(",
                            "request.financial(", "request.dividends(",
                            "request.splits(", "request.earnings(",
                            "request.quandl(", "request.economic("))
    return used


def project_dirs(explicit):
    if explicit:
        p = Path(explicit)
        return [p if p.is_absolute() else ROOT / p]
    out = []
    for base in SEARCH_DIRS:
        d = ROOT / base
        if d.is_dir():
            out += [c for c in sorted(d.iterdir()) if (c / "version.json").exists()]
    return out


def source_for(project):
    src = project / "src"
    if not src.is_dir():
        return None
    version = project / "version.json"
    if version.exists():
        name = json.loads(version.read_text(encoding="utf-8"))["name"]
        candidate = src / f"{name}.pine"
        if candidate.exists():
            return candidate
    found = sorted(src.glob("*.pine"))
    return found[0] if len(found) == 1 else None


def main():
    parser = argparse.ArgumentParser(description="Check projects against their budgets.")
    parser.add_argument("project", nargs="?")
    parser.add_argument("--init", action="store_true",
                        help="Write budget.json from current usage (never above the platform max)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

    projects = project_dirs(args.project)
    if not projects:
        print("no projects found")
        return 0

    report, breaches, undeclared = [], [], []
    for project in projects:
        source = source_for(project)
        if source is None:
            continue
        used = measure(source)
        budget_file = project / "budget.json"

        if args.init:
            budget = {k: min(max(v, 1), PLATFORM_MAX[k]) for k, v in used.items()}
            budget_file.write_text(json.dumps({
                "_comment": ("Declared resource budget. These are intentions, not "
                             "TradingView's limits — going over one means a change "
                             "used more than this project meant to."),
                "budget": budget,
            }, indent=2) + "\n", encoding="utf-8")
            print(f"wrote {budget_file.relative_to(ROOT)}")
            continue

        if not budget_file.exists():
            undeclared.append(project.name)
            report.append({"project": project.name, "status": "no-budget", "used": used})
            continue

        budget = json.loads(budget_file.read_text(encoding="utf-8"))["budget"]
        over = {k: (v, budget[k]) for k, v in used.items()
                if k in budget and v > budget[k]}
        if over:
            breaches.append((project.name, over))
        report.append({"project": project.name,
                       "status": "over" if over else "ok",
                       "used": used, "budget": budget})

    if args.init:
        return 0

    if args.json:
        print(json.dumps({"projects": report, "over_budget": [b[0] for b in breaches],
                          "undeclared": undeclared}, indent=2))
        return 1 if breaches else 0

    for entry in report:
        if entry["status"] == "no-budget":
            print(f"{entry['project']}: no budget.json "
                  f"(create one with --init)")
            continue
        mark = "OVER" if entry["status"] == "over" else "ok  "
        u = entry["used"]
        print(f"{mark} {entry['project']:<28} boxes {u['boxes']:>3}  lines {u['lines']:>3}  "
              f"labels {u['labels']:>3}  plots {u['plot_counts']:>3}  req {u['requests']:>2}")
    for name, over in breaches:
        for key, (value, limit) in over.items():
            print(f"{name}: {key} = {value}, over its declared budget of {limit}")
    print()
    print(f"{len(report)} project(s) checked against budget, {len(breaches)} over, "
          f"{len(undeclared)} undeclared.")
    return 1 if breaches else 0


if __name__ == "__main__":
    raise SystemExit(main())
