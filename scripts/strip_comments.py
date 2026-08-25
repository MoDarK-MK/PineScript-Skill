"""Remove comments from a Pine script, for the RELEASE copy only.

This repo writes a lot of prose into its scripts on purpose - why a bound
exists, what was measured, which bug a line prevents. That belongs in the
source, where it is read by whoever changes the code. It does not belong in the
copy that gets pasted into TradingView, where it is several hundred lines of
text between the reader and the code.

So the source keeps every word and the release keeps none.

Two things survive, because they are not really comments:

  * `//@version=N`, which is a compiler directive. Removing it changes which
    language the script is compiled as.
  * The licence header and the copyright line, which TradingView's own template
    puts there and which say who owns the work.

The hard part is that `//` inside a string is not a comment:

    plot(close, title = "https://example.com")

Cutting at the first `//` there produces an unterminated string literal and a
script that will not compile. Every line is walked character by character with
the string state tracked, never split on a substring.

Usage:
    python3 scripts/strip_comments.py FILE          # to stdout
    python3 scripts/strip_comments.py FILE --check  # report what would go
"""
import argparse
import re
import sys

VERSION_RE = re.compile(r'^\s*//\s*@version\s*=')
# Both of TradingView's own wordings. The newer template writes "This Pine
# Script®", the older one "This source code", and matching only the first
# silently dropped the licence from every project scaffolded before the change.
LICENCE_RE = re.compile(
    r'^\s*//\s*(This (Pine Script|source code)|©|\(c\)|Copyright|SPDX-)',
    re.IGNORECASE)


def code_before_comment(line):
    """The line with any trailing comment removed, string-aware.

    Returns the code part only. A `//` inside a string literal is text, not the
    start of a comment, and treating it as one is how a tooltip containing a URL
    turns into a compile error."""
    in_str = None
    i = 0
    while i < len(line):
        ch = line[i]
        if in_str:
            if ch == "\\" and i + 1 < len(line):
                i += 2
                continue
            if ch == in_str:
                in_str = None
        elif ch in ('"', "'"):
            in_str = ch
        elif ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
            return line[:i]
        i += 1
    return line


def strip_pine_comments(text):
    """Every comment gone except the version directive and the licence header.

    Comment-only lines are removed rather than left blank, and runs of blank
    lines are collapsed to one, because the point is a shorter file and not a
    file of the same length with holes in it."""
    lines = text.split("\n")
    out = []
    for raw in lines:
        stripped = raw.strip()
        # A licence or copyright line is kept WHEREVER it appears, not only in
        # a leading header. The part builder writes the version directive first
        # and the licence after it, so protecting only a leading block removed
        # the licence from every generated project.
        if VERSION_RE.match(raw) or LICENCE_RE.match(raw):
            out.append(raw.rstrip())
            continue
        code = code_before_comment(raw).rstrip()
        if code:
            out.append(code)
        elif not stripped:
            out.append("")
        # A comment-only line contributes nothing at all.

    # Collapse blank runs, and do not leave the file starting or ending on one.
    collapsed = []
    for line in out:
        if not line and collapsed and not collapsed[-1]:
            continue
        collapsed.append(line)
    while collapsed and not collapsed[0]:
        collapsed.pop(0)
    while collapsed and not collapsed[-1]:
        collapsed.pop()
    return "\n".join(collapsed) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Strip comments from a Pine script.")
    ap.add_argument("file")
    ap.add_argument("--check", action="store_true",
                    help="Report the line counts instead of printing the result")
    args = ap.parse_args(argv)

    with open(args.file, encoding="utf-8") as fh:
        text = fh.read()
    result = strip_pine_comments(text)
    if args.check:
        before = len(text.split("\n"))
        after = len(result.split("\n"))
        print(f"{args.file}: {before} lines -> {after} ({before - after} removed)")
        return 0
    sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
