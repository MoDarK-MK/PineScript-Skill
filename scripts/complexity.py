#!/usr/bin/env python3
"""
complexity.py - Report the shape of a Pine file before it becomes unworkable.

Pine has no modules. Everything lives in one file, so a script that keeps
growing has nowhere to go, and the file that produced this repo's worst bug so
far — a declaration ordered below its reader — was 1680 lines long. Nobody
decided it should be; it arrived there one feature at a time.

This measures the things that make a file hard to hold in your head, and fails
above configurable thresholds so the growth is a decision rather than a drift.

Usage:
    python3 scripts/complexity.py                 # report every project
    python3 scripts/complexity.py FILE            # one file
    python3 scripts/complexity.py --check         # exit 1 over threshold
    python3 scripts/complexity.py --json
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pine_lint

ROOT = Path(__file__).resolve().parent.parent

# Advisory thresholds: where a file starts being genuinely awkward to hold in
# your head. Exceeding one is REPORTED but never fails a run, because a
# repo-wide number applied to an existing codebase either fails from day one or
# is set so loose it never fires.
#
# What fails is a project exceeding the limit IT declared, in its own
# budget.json. That is a ratchet: it catches a file getting worse than the
# project said it should be, which is the thing worth knowing. Raising a
# declared limit is then a visible decision in a diff rather than a drift.
THRESHOLDS = {
    "lines": 1200,
    "longest_function": 80,
    "max_indent_depth": 6,
    "inputs": 80,
    "top_level_blocks": 40,
}
DECLARED_KEYS = ("lines", "longest_function", "max_indent_depth", "inputs")

SEARCH_DIRS = ("indicators", "strategies", "libraries", "assets")


def display_path(path):
    """Repo-relative when it is inside the repo, absolute when it is not.

    relative_to() RAISES on a path outside the tree, so a project living
    anywhere else — a scratch directory, a test fixture, a second checkout —
    crashed the tool on its success message."""
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def measure(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    stripped = [pine_lint.strip_strings_and_comments(l) for l in lines]

    code_lines = [l for l in stripped if l.strip()]

    # `export foo() =>` is a function too. iter_function_bodies() only sees the
    # bare form, which reported a library of 15 helpers as having none.
    def bodies():
        seen = {i for i, _b in pine_lint.iter_function_bodies(lines)}
        for i, _b in pine_lint.iter_function_bodies(lines):
            yield i, _b
        for i, text in enumerate(stripped):
            if i in seen or not text.strip().startswith("export "):
                continue
            if not pine_lint.FUNC_NAME_RE.match(text.strip()[len("export "):]):
                continue
            body = []
            j = i + 1
            while j < len(lines):
                if not stripped[j].strip():
                    j += 1
                    continue
                if pine_lint.indent_width(lines[j]) == 0:
                    break
                body.append((j, stripped[j]))
                j += 1
            yield i, body

    all_bodies = list(bodies())
    longest, longest_name = 0, ""
    for decl_idx, body in all_bodies:
        head = stripped[decl_idx].strip()
        head = head[len("export "):] if head.startswith("export ") else head
        m = pine_lint.FUNC_NAME_RE.match(head)
        if len(body) > longest:
            longest, longest_name = len(body), (m.group(1) if m else "?")

    depth = 0
    for raw, text in zip(lines, stripped):
        if text.strip():
            depth = max(depth, pine_lint.indent_width(raw) // 4)

    statements = pine_lint.build_logical_statements(lines)
    inputs = sum(1 for s in statements if re.search(r'\binput\s*\.', s["stripped"]))
    top_level = sum(1 for raw, text in zip(lines, stripped)
                    if text.strip() and pine_lint.indent_width(raw) == 0
                    and re.match(r'^(if|for|while|switch)\b', text.strip()))

    return {
        "file": display_path(path),
        "lines": len(lines),
        "code_lines": len(code_lines),
        "functions": len(all_bodies),
        "longest_function": longest,
        "longest_function_name": longest_name,
        "max_indent_depth": depth,
        "inputs": inputs,
        "top_level_blocks": top_level,
    }


def over_threshold(m):
    return {k: (m[k], THRESHOLDS[k]) for k in THRESHOLDS if m.get(k, 0) > THRESHOLDS[k]}


def declared_limits(path):
    """The project's own complexity limits from budget.json, or None."""
    for parent in path.parents:
        budget = parent / "budget.json"
        if budget.exists():
            data = json.loads(budget.read_text(encoding="utf-8"))
            return parent.name, data.get("complexity")
        if parent == ROOT:
            break
    return None, None


def over_declared(m, limits):
    if not limits:
        return {}
    return {k: (m[k], limits[k]) for k in DECLARED_KEYS
            if k in limits and m.get(k, 0) > limits[k]}


def targets(explicit):
    if explicit:
        return [Path(explicit)]
    found = []
    for base in SEARCH_DIRS:
        d = ROOT / base
        if d.is_dir():
            found += [p for p in sorted(d.rglob("*.pine"))
                      if "release" not in p.parts and "fixtures" not in p.parts
                      and "parts" not in p.parts]
    return found


def main():
    parser = argparse.ArgumentParser(description="Report Pine file complexity.")
    parser.add_argument("file", nargs="?")
    parser.add_argument("--check", action="store_true",
                        help="Exit 1 if a project exceeds its DECLARED limit")
    parser.add_argument("--update-baseline", action="store_true",
                        help="Record current values as each project's declared limit")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

    files = targets(args.file)
    if not files:
        print("no .pine files found", file=sys.stderr)
        return 0

    reports = [measure(p) for p in files]
    advisory = {r["file"]: over_threshold(r) for r in reports}
    advisory = {f: b for f, b in advisory.items() if b}

    breaches, undeclared = {}, []
    for path, r in zip(files, reports):
        project, limits = declared_limits(path)
        if limits is None:
            if project:
                undeclared.append(project)
            continue
        over = over_declared(r, limits)
        if over:
            breaches[r["file"]] = over

    if args.update_baseline:
        written = 0
        for path, r in zip(files, reports):
            for parent in path.parents:
                budget = parent / "budget.json"
                if budget.exists():
                    data = json.loads(budget.read_text(encoding="utf-8"))
                    data["complexity"] = {k: r[k] for k in DECLARED_KEYS}
                    budget.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                    written += 1
                    break
                if parent == ROOT:
                    break
        print(f"recorded current complexity into {written} budget.json file(s)")
        print("Read the diff: every number here is now a limit you are agreeing to.")
        return 0

    if args.json:
        print(json.dumps({
            "thresholds": THRESHOLDS, "files": reports,
            "over_advisory": {f: {k: v[0] for k, v in b.items()} for f, b in advisory.items()},
            "over_declared": {f: {k: v[0] for k, v in b.items()} for f, b in breaches.items()},
            "undeclared": sorted(set(undeclared)),
        }, indent=2))
        return 1 if (args.check and breaches) else 0

    header = f"{'file':<52}{'lines':>7}{'fns':>5}{'longest':>9}{'depth':>7}{'inputs':>8}"
    print(header)
    print("-" * len(header))
    for r in sorted(reports, key=lambda x: -x["lines"]):
        print(f"{r['file']:<52}{r['lines']:>7}{r['functions']:>5}"
              f"{r['longest_function']:>9}{r['max_indent_depth']:>7}{r['inputs']:>8}")
    print()
    for f, b in advisory.items():
        for key, (value, limit) in b.items():
            print(f"note  {f}: {key} = {value}, past the {limit} advisory threshold")
    if advisory:
        print("      (advisory only — a prompt to split the file into parts with")
        print("       scripts/build_pine.py, never a failure on its own)")
        print()
    for f, b in breaches.items():
        for key, (value, limit) in b.items():
            print(f"OVER  {f}: {key} = {value}, over its DECLARED limit of {limit}")
    if breaches:
        print()
        print("Raise the limit in that project's budget.json if the growth is intended.")
        print("Doing it there makes the decision visible in a diff.")
    print(f"{len(reports)} file(s) measured, {len(advisory)} past advisory, "
          f"{len(breaches)} over declared.")
    return 1 if (args.check and breaches) else 0


if __name__ == "__main__":
    raise SystemExit(main())
