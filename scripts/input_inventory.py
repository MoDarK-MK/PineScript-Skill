#!/usr/bin/env python3
"""
input_inventory.py - Extract every input.*() from a Pine script into a table.

Two jobs. The first is documentation: a published indicator's settings panel is
its user interface, and a table of what every control does is most of the
TradingView publish description written for you. The second is review: gaps that
are invisible while scrolling source — a group where nothing is explained, a
numeric input with no bound — line up in a column and become obvious.

Usage:
    python3 input_inventory.py path/to/script.pine
    python3 input_inventory.py path/to/project        # finds src/<name>.pine
    python3 input_inventory.py FILE --out release/INPUTS.md
    python3 input_inventory.py FILE --json
"""
import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import pine_lint  # noqa: E402

INPUT_ASSIGN_RE = re.compile(
    r'(?:^|\s)(?:(?:var|varip)\s+)?(?:\w+(?:<[^>]*>)?\s+)?'
    r'([A-Za-z_]\w*)\s*=\s*input\s*(?:\.\s*(\w+))?\s*\(')

UNGROUPED = "(no group)"


STRING_LITERAL_RE = re.compile(r'"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'')
STRING_CONST_RE = re.compile(
    r'^\s*(?:var\s+)?(?:string\s+)?([A-Za-z_]\w*)\s*=\s*("(?:[^"\\]|\\.)*")\s*$')


def _literal(text, consts=None):
    """Resolves an argument expression to display text.

    Pine has no multi-line string literal, so every long tooltip in this repo is
    written as `"part one " + "part two"`. Returning that expression verbatim —
    quotes, plus signs and all — is what the first version of this script did,
    and the tables it produced were unreadable."""
    if text is None:
        return None
    text = text.strip()
    if consts and text in consts:
        return consts[text]
    pieces = STRING_LITERAL_RE.findall(text)
    if pieces:
        # Only treat it as a string expression when the literals are all there
        # is — otherwise a call like str.tostring(x, "#.##") would be reduced to
        # its format string.
        without = STRING_LITERAL_RE.sub("", text)
        if not re.search(r'[A-Za-z0-9_]', without):
            joined = "".join(a or b for a, b in pieces)
            return joined.replace('\\"', '"').replace("\\n", " ")
    return text


def collect_string_constants(lines):
    """Maps a constant name to its string value, so `group = SW_GROUP` renders
    as the section heading the user actually sees in the settings panel."""
    consts = {}
    for raw in lines:
        m = STRING_CONST_RE.match(pine_lint.strip_comments_only(raw))
        if m:
            consts[m.group(1)] = m.group(2)[1:-1]
    return consts


def extract_inputs(text):
    """Returns a list of dicts, one per input.*() call, in source order."""
    lines = text.splitlines()
    statements = pine_lint.build_logical_statements(lines)
    consts = collect_string_constants(lines)
    found = []
    for stmt in statements:
        joined = pine_lint.strip_comments_only_multi(stmt["raw_nc"])
        m = INPUT_ASSIGN_RE.search(joined)
        if not m:
            continue
        var_name, kind = m.group(1), m.group(2) or "generic"
        call = f"input.{kind}(" if m.group(2) else "input("
        arg_text = pine_lint.call_arg_text(joined, call)
        if arg_text is None:
            continue
        args = pine_lint.split_top_level_args(arg_text)
        positional = pine_lint.positional_args(args)

        def named(name):
            return pine_lint.named_arg(args, name)

        title = named("title")
        if title is None and len(positional) > 1:
            title = positional[1]
        default = named("defval")
        if default is None and positional:
            default = positional[0]

        found.append({
            "variable": var_name,
            "type": kind,
            # Kept distinct from a MISSING title: an empty one is legitimate
            # for a colour picker sharing an inline row with its label.
            "title": _literal(title, consts) if title is not None else None,
            "default": _literal(default, consts),
            "group": _literal(named("group"), consts) or UNGROUPED,
            "inline": _literal(named("inline"), consts),
            "minval": _literal(named("minval"), consts),
            "maxval": _literal(named("maxval"), consts),
            "step": _literal(named("step"), consts),
            "options": _literal(named("options"), consts),
            "tooltip": _literal(named("tooltip"), consts),
            "line": stmt["start"],
        })
    return found


def group_order(inputs):
    """Groups in first-appearance order — the order the settings panel shows."""
    seen = []
    for item in inputs:
        if item["group"] not in seen:
            seen.append(item["group"])
    return seen


def _range_cell(item):
    lo, hi, step = item["minval"], item["maxval"], item["step"]
    if item["options"]:
        return "choice"
    if lo is None and hi is None:
        return "—"
    span = f"{lo if lo is not None else '−∞'} … {hi if hi is not None else '∞'}"
    return f"{span} (step {step})" if step else span


def cell(value):
    """Escapes a value for a Markdown table cell.

    A pipe inside a title ("Sell | Buy") silently splits the row into an extra
    column — which is exactly how a generated table quietly lies."""
    if value is None or value == "":
        return "—"
    return str(value).replace("|", r"\|").replace("\n", " ")


def render_markdown(inputs, title):
    out = [f"# {title} — Inputs", ""]
    if not inputs:
        out.append("This script has no inputs.")
        return "\n".join(out) + "\n"

    documented = sum(1 for i in inputs if i["tooltip"])
    out.append(f"{len(inputs)} input(s) across {len(group_order(inputs))} group(s). "
               f"{documented} carry a tooltip.")
    out.append("")
    out.append("Generated by `scripts/input_inventory.py` — do not edit by hand.")
    out.append("")

    for group in group_order(inputs):
        out.append(f"## {group}")
        out.append("")
        out.append("| Setting | Type | Default | Range | What it does |")
        out.append("|---|---|---|---|---|")
        for item in (i for i in inputs if i["group"] == group):
            tip = cell(item["tooltip"])
            if len(tip) > 300:
                tip = tip[:297] + "…"
            out.append(
                f"| {cell(item['title'] or item['variable'])} | {item['type']} | "
                f"`{cell(item['default'])}` | "
                f"{_range_cell(item)} | {tip} |")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def resolve_source(target):
    """Accepts a .pine file or a project directory."""
    path = Path(target)
    if path.is_file():
        return path
    if path.is_dir():
        version = path / "version.json"
        if version.exists():
            name = json.loads(version.read_text(encoding="utf-8"))["name"]
            candidate = path / "src" / f"{name}.pine"
            if candidate.exists():
                return candidate
        candidates = sorted((path / "src").glob("*.pine")) if (path / "src").is_dir() else []
        if len(candidates) == 1:
            return candidates[0]
    return None


def main():
    pine_lint.make_output_encoding_safe()
    parser = argparse.ArgumentParser(description="Tabulate a Pine script's inputs.")
    parser.add_argument("target", help="A .pine file, or a project directory")
    parser.add_argument("--out", default=None, help="Write Markdown here instead of stdout")
    parser.add_argument("--json", action="store_true", help="Emit the raw records as JSON")
    args = parser.parse_args()

    source = resolve_source(args.target)
    if source is None:
        print(f"error: no .pine source found at {args.target}", file=sys.stderr)
        return 1

    inputs = extract_inputs(source.read_text(encoding="utf-8"))
    if args.json:
        print(json.dumps(inputs, indent=2, ensure_ascii=False))
        return 0

    markdown = render_markdown(inputs, source.stem)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(markdown, encoding="utf-8")
        print(f"Wrote {len(inputs)} input(s) to {args.out}")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
