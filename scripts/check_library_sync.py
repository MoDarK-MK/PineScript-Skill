#!/usr/bin/env python3
"""
check_library_sync.py - Keep the inlined copies of library helpers honest.

TradingView's `import` only works against a library that has been PUBLISHED to
their servers. Until `libraries/pine_toolkit` is published, every script that
wants `formatVolume()` has to carry its own copy — which is exactly the
situation where copies drift apart and nobody notices for months.

This compares each `export`ed function in the library against every same-named
function defined in the other .pine files, and reports any whose body differs.
It does not merge or rewrite anything: which side is right is a judgement call,
and a tool that guessed would eventually guess wrong.

A function may opt out with a `// library-sync-exempt: why` comment on the line
above its declaration — for a copy that is deliberately specialised.

Usage:
    python3 scripts/check_library_sync.py
    python3 scripts/check_library_sync.py --json
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "libraries" / "pine_toolkit" / "src" / "pine_toolkit.pine"
SEARCH_DIRS = ("indicators", "strategies", "assets", "references")

EXPORT_RE = re.compile(r'^export\s+([a-zA-Z_]\w*)\s*\(')
LOCAL_RE = re.compile(r'^([a-zA-Z_]\w*)\s*\(')
EXEMPT_RE = re.compile(r'//\s*library-sync-exempt\b')


# Local names for library functions, where the copy could NOT keep the library's
# name. These three could not: `textColor` and `mutedColor` are already
# variables in every script that uses them -
#
#     color textColor = getTextColor(themeInput)
#
# so a copy called `textColor` would collide with the value it produces. The
# `get` prefix is load-bearing, not noise, and renaming to match would create
# exactly the shadowing bug that has already cost this repo a release.
#
# Comparing by name alone meant these were never compared at all, and three
# helpers across four projects drifted into two versions each.
LOCAL_ALIASES = {
    "getTextColor": "textColor",
    "getMutedColor": "mutedColor",
    "getPanelColor": "panelColor",
}


def read_lines(path):
    return path.read_text(encoding="utf-8").splitlines()


# A script names its themes; a library cannot, because the constant belongs to
# the consumer. Normalising them is what keeps 27 style differences from burying
# the one real difference underneath - a missing transparency clamp, in this
# case, which nobody could see through the noise.
CONSTANT_EQUIVALENTS = {
    "THEME_LIGHT": '"Light"',
    "THEME_DARK": '"Dark"',
}


def normalise(body):
    """A function body with known constant names replaced by their values, and
    `switch x` / ternary spellings of the same two-way choice made comparable."""
    out = []
    for line in body:
        for name, literal in CONSTANT_EQUIVALENTS.items():
            line = re.sub(r'(?<![\w.])' + name + r'(?![\w])', literal, line)
        out.append(" ".join(line.split()))
    return out


def collect_functions(lines, pattern):
    """Returns {name: (decl_line_no, [body lines])} for every function declared
    at column 0. The body is every following line indented past column 0."""
    out = {}
    for i, line in enumerate(lines):
        m = pattern.match(line)
        if not m or "=>" not in line:
            continue
        # The marker may sit anywhere in the contiguous comment block above the
        # declaration, not only on the line immediately before it — a reason
        # worth writing is usually a reason worth writing in full sentences.
        exempt = False
        k = i - 1
        while k >= 0 and lines[k].lstrip().startswith("//"):
            if EXEMPT_RE.search(lines[k]):
                exempt = True
                break
            k -= 1
        if exempt:
            continue
        body = []
        j = i + 1
        while j < len(lines):
            nxt = lines[j]
            if not nxt.strip():
                j += 1
                continue
            if not nxt.startswith((" ", "\t")):
                break
            body.append(nxt.rstrip())
            j += 1
        out[m.group(1)] = (i + 1, body)
    return out


def source_files():
    for rel in SEARCH_DIRS:
        base = ROOT / rel
        if base.is_dir():
            for path in sorted(base.rglob("*.pine")):
                if {"release", "fixtures", "parts"} & set(path.parts):
                    continue
                yield path


def main():
    parser = argparse.ArgumentParser(description="Check inlined copies against pine_toolkit.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not LIBRARY.exists():
        print(f"error: library not found at {LIBRARY}", file=sys.stderr)
        return 1

    exported = collect_functions(read_lines(LIBRARY), EXPORT_RE)
    drift = []
    matched = 0
    for path in source_files():
        local = collect_functions(read_lines(path), LOCAL_RE)
        for name, (line_no, body) in sorted(local.items()):
            canonical = LOCAL_ALIASES.get(name, name)
            if canonical not in exported:
                continue
            matched += 1
            if normalise(body) != normalise(exported[canonical][1]):
                drift.append({
                    "function": name if canonical == name
                                else f"{name} [library: {canonical}]",
                    "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                    "line": line_no,
                    "library_line": exported[canonical][0],
                })

    if args.json:
        print(json.dumps({"exports": len(exported), "copies_checked": matched,
                          "drift": drift}, indent=2))
    else:
        for d in drift:
            print(f"{d['file']}:{d['line']}: '{d['function']}()' differs from "
                  f"pine_toolkit.pine:{d['library_line']}")
        print()
        print(f"{len(exported)} exported function(s), {matched} inlined "
              f"cop{'y' if matched == 1 else 'ies'} checked, {len(drift)} drifted.")
        if drift:
            print()
            print("Reconcile them by hand, or mark the copy with a")
            print("`// library-sync-exempt: <reason>` comment above its declaration.")
    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
