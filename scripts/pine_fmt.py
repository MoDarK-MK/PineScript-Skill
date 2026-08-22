#!/usr/bin/env python3
"""
pine_fmt.py - Formatter for TradingView Pine Script.

references/style-guide.md was prose only. Prose is not a mechanism: it gets read
once and then drifts. This applies the mechanical half of it, and `--check` in
CI is what makes it stick.

WHAT IT DELIBERATELY DOES NOT DO, and why:

  Block indentation. Pine uses indentation to define blocks, so re-indenting is
  re-structuring. A formatter that gets it wrong does not produce ugly code, it
  produces different code.

  Continuation indents. A wrapped line NOT inside parentheses must be indented
  by an amount that is NOT a multiple of 4, or Pine reads it as a new block.
  That rule is real, it is subtle, and no safe automatic rewrite exists for it.

  Spaces around `=` in named arguments. TradingView's style guide asks for
  `plot(series = close)`; every file in this repo writes `plot(series=close)`.
  Imposing either one would rewrite thousands of lines to settle a question of
  taste, so the formatter leaves `=` alone entirely.

What is left is small on purpose. Everything here is a substitution that cannot
change the meaning of a line.

Usage:
    python3 pine_fmt.py FILE [FILE ...]        # rewrite in place
    python3 pine_fmt.py FILE --check           # exit 1 if anything would change
    python3 pine_fmt.py FILE --diff            # show the changes, write nothing
"""
import argparse
import difflib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import re  # noqa: E402

from pine_lint import (  # noqa: E402
    _replace_outside_strings,
    make_output_encoding_safe,
)

# A comma not already followed by a space, a closing bracket, or end of line.
COMMA_RE = re.compile(r',(?=[^\s)\]])')
# Multi-character operators only. Bare < and > are excluded on purpose: they
# also open and close generic type parameters (`array<float>`), and spacing
# those would produce code Pine cannot parse.
#
# These only ADD a missing space, never remove an existing one. That asymmetry
# is not fussiness: this repo aligns `=` into columns across a block of inputs,
# and a formatter that collapses runs of spaces would destroy every one of them
# while believing it was tidying up.
OP_NEEDS_LEFT = re.compile(r'(?<=[^\s=!<>:])(==|!=|>=|<=|:=)')
OP_NEEDS_RIGHT = re.compile(r'(==|!=|>=|<=|:=)(?=[^\s=])')
MAX_BLANK_RUN = 2


def format_line(raw):
    """Formats one physical line. Never changes its indentation depth."""
    line = raw.rstrip()

    lead_tabs = len(line) - len(line.lstrip("\t"))
    if lead_tabs:
        line = "    " * lead_tabs + line[lead_tabs:]

    line, _n = _replace_outside_strings(line, COMMA_RE, ", ")

    line, _n = _replace_outside_strings(line, OP_NEEDS_LEFT, r" \1")
    line, _n = _replace_outside_strings(line, OP_NEEDS_RIGHT, r"\1 ")
    return line.rstrip()


def format_text(text):
    """Formats a whole file's text. Returns the formatted text."""
    lines = [format_line(l) for l in text.splitlines()]

    out = []
    blanks = 0
    for line in lines:
        if line.strip():
            blanks = 0
            out.append(line)
            continue
        blanks += 1
        if blanks <= MAX_BLANK_RUN:
            out.append(line)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out) + "\n" if out else ""


def process(path, mode):
    original = Path(path).read_text(encoding="utf-8")
    formatted = format_text(original)
    if formatted == original:
        return 0, False
    if mode == "diff" or mode == "check":
        if mode == "diff":
            sys.stdout.writelines(difflib.unified_diff(
                original.splitlines(keepends=True),
                formatted.splitlines(keepends=True),
                fromfile=f"{path} (current)", tofile=f"{path} (formatted)"))
        return 0, True
    Path(path).write_text(formatted, encoding="utf-8")
    return 0, True


def main():
    make_output_encoding_safe()
    parser = argparse.ArgumentParser(description="Formatter for Pine Script.")
    parser.add_argument("files", nargs="+", help="One or more .pine files")
    parser.add_argument("--check", action="store_true",
                        help="Exit 1 if any file would change; write nothing")
    parser.add_argument("--diff", action="store_true",
                        help="Print the changes that would be made; write nothing")
    args = parser.parse_args()

    mode = "check" if args.check else "diff" if args.diff else "write"
    changed = []
    for f in args.files:
        if not Path(f).exists():
            print(f"error: file not found: {f}", file=sys.stderr)
            return 1
        _rc, did = process(f, mode)
        if did:
            changed.append(f)

    if mode == "check":
        if changed:
            for f in changed:
                print(f"{f}: not formatted")
            print(f"\n{len(changed)} file(s) need formatting. "
                  f"Run: python3 scripts/pine_fmt.py {' '.join(changed)}")
            return 1
        print(f"{len(args.files)} file(s) already formatted.")
        return 0

    if mode == "write":
        for f in changed:
            print(f"formatted {f}")
        print(f"\n{len(changed)} of {len(args.files)} file(s) changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
