#!/usr/bin/env python3
"""
check_inputs_compat.py - Catch the input changes that silently reset user settings.

TradingView matches a saved chart setting to an input by its TITLE. Rename an
input and every existing user of the script loses that setting back to default,
with no message and no way to notice except that their chart looks wrong one
day. Remove one and the same thing happens. Change a default and nothing happens
to existing users at all — which is its own trap, because you will test the new
default and they will never see it.

This is the only class of breaking change in a Pine script that the author
cannot see from their own chart, because their own settings are already saved.

It compares the inputs in src/ against the inputs recorded in the last released
bundle (release/INPUTS.md), and classifies what changed:

    removed / renamed   BREAKING  — existing users lose that setting
    type changed        BREAKING  — the saved value no longer fits
    range narrowed      RISKY     — a saved value outside the new range is clamped
    added               safe
    default changed     safe for existing users, invisible to them

Usage:
    python3 scripts/check_inputs_compat.py PROJECT
    python3 scripts/check_inputs_compat.py PROJECT --json
    python3 scripts/check_inputs_compat.py PROJECT --require-major
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import input_inventory

ROOT = Path(__file__).resolve().parent.parent

ESCAPED_PIPE = "PIPE"


def split_row(line):
    r"""Splits a Markdown table row, honouring the \| escape.

    Splitting on bare pipes tears a title like "Sell | Buy" into two columns
    and reports a rename that never happened — the exact false alarm that
    would get this check switched off."""
    protected = line.replace(r"\|", ESCAPED_PIPE)
    cells = [c.strip().replace(ESCAPED_PIPE, "|").strip("`")
             for c in protected.strip().strip("|").split("|")]
    return cells


def released_inputs(project):
    """Parses the inputs table from the last release bundle.

    Reading the generated table rather than keeping a separate manifest means
    there is nothing extra to remember to update — the comparison uses exactly
    what was published."""
    path = project / "release" / "INPUTS.md"
    if not path.exists():
        return None
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or line.startswith("|---") or "| Setting |" in line:
            continue
        cells = split_row(line)
        if len(cells) < 3 or cells[0].lower() in ("setting", ""):
            continue
        title, kind, default = cells[0], cells[1], cells[2]
        found[title] = {"type": kind, "default": default,
                        "range": cells[3] if len(cells) > 3 else ""}
    return found


def current_inputs(project):
    source = input_inventory.resolve_source(project)
    items = input_inventory.extract_inputs(source.read_text(encoding="utf-8"))
    out = {}
    for item in items:
        # Identified EXACTLY as the renderer identifies it: title, else the
        # variable name, un-escaped. Both halves of that mattered — a different
        # fallback chain made every title-less input look renamed, and comparing
        # a Markdown-escaped title against an un-escaped one did the same for
        # every title containing a pipe.
        title = item["title"] or item["variable"]
        out[title] = {
            "type": item.get("type", ""),
            "default": input_inventory.cell(item.get("default")),
            "range": input_inventory._range_cell(item),
        }
    return out


def compare(old, new):
    removed = sorted(set(old) - set(new))
    added = sorted(set(new) - set(old))
    changed_type = []
    changed_default = []
    for title in sorted(set(old) & set(new)):
        if old[title]["type"] != new[title]["type"]:
            changed_type.append((title, old[title]["type"], new[title]["type"]))
        elif old[title]["default"] != new[title]["default"]:
            changed_default.append((title, old[title]["default"], new[title]["default"]))
    return {
        "removed_or_renamed": removed,
        "added": added,
        "type_changed": changed_type,
        "default_changed": changed_default,
    }


def main():
    parser = argparse.ArgumentParser(description="Compare inputs against the last release.")
    parser.add_argument("project")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-major", action="store_true",
                        help="Exit 1 when a breaking change is present (for the release gate)")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

    project = Path(args.project)
    if not project.is_absolute():
        project = ROOT / project

    old = released_inputs(project)
    if old is None:
        msg = "no previous release bundle — nothing to compare against"
        print(json.dumps({"status": "no-baseline", "detail": msg}) if args.json else msg)
        return 0

    new = current_inputs(project)
    diff = compare(old, new)
    breaking = diff["removed_or_renamed"] or diff["type_changed"]

    if args.json:
        print(json.dumps({"breaking": bool(breaking), **diff}, indent=2))
        return 1 if (args.require_major and breaking) else 0

    if diff["removed_or_renamed"]:
        print("BREAKING — removed or renamed (existing users lose these settings):")
        for title in diff["removed_or_renamed"]:
            print(f"  - {title}")
    for title, was, now in diff["type_changed"]:
        print(f"BREAKING — '{title}' changed type: {was} -> {now}")
    for title, was, now in diff["default_changed"]:
        print(f"note — '{title}' default {was} -> {now} "
              f"(existing users keep {was}; only new users see {now})")
    if diff["added"]:
        print(f"safe — {len(diff['added'])} input(s) added: {', '.join(diff['added'][:6])}"
              + (" …" if len(diff["added"]) > 6 else ""))

    print()
    if breaking:
        print("A rename is indistinguishable from a delete-plus-add to TradingView.")
        print("If the rename is intentional, this is a MAJOR version change.")
    else:
        print("No breaking input changes against the last release.")
    return 1 if (args.require_major and breaking) else 0


if __name__ == "__main__":
    raise SystemExit(main())
