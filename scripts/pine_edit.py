"""Edit a Pine file without the shell eating the backslashes.

Every tool that writes Pine goes through a shell somewhere, and a shell removes
one level of backslash escaping on the way past. Writing `\\n` in an edit command
therefore lands as `\n` in the file, which Python or Pine then reads as an
actual newline - and a real newline inside a Pine string literal is
`Missing enclosing character in the literal string`, a hard compile failure.

That happened five separate times while building this repo. PINE059 now catches
it after the fact; this stops it happening.

The whole idea is that escape sequences are never typed. An edit is JSON, and
where a Pine string needs a line break the JSON says so structurally:

    python3 scripts/pine_edit.py FILE --edits edits.json

    [{"find": "tooltip=\\"old\\"",
      "replace": ["tooltip=\\"first line.", {"nl": 2}, "second line.\\""]}]

A replacement given as a LIST is joined with nothing between the parts, and
`{"nl": n}` becomes n literal backslash-n sequences - the two characters Pine
wants, produced from a character code so no shell can touch them.

Every edit must match exactly once. An edit that matches twice is ambiguous and
an edit that matches nothing is stale, and both are refused rather than guessed.

    --check   report what would change, write nothing
"""
import argparse
import json
import sys
from pathlib import Path

BACKSLASH = chr(92)


def render(part):
    """One piece of a replacement, as text.

    A dict is a structural instruction, so the caller never has to type an
    escape sequence and no shell ever sees one."""
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        if "nl" in part:
            return (BACKSLASH + "n") * int(part["nl"])
        if "tab" in part:
            return (BACKSLASH + "t") * int(part["tab"])
        if "quote" in part:
            return (BACKSLASH + '"') * int(part["quote"])
        if "backslash" in part:
            return (BACKSLASH * 2) * int(part["backslash"])
        raise ValueError(f"unknown instruction: {sorted(part)}")
    raise ValueError(f"a replacement part must be a string or an instruction, "
                     f"got {type(part).__name__}")


def build(value):
    """A replacement, which may be a string or a list of parts."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(render(p) for p in value)
    raise ValueError("replace must be a string or a list")


def unterminated_line(text):
    """The first line number holding a string that never closes, or None.

    The check runs on the RESULT, before anything is written. This tool exists
    because that fault is easy to introduce and invisible to read, so it refuses
    to be the thing that introduces it."""
    for number, line in enumerate(text.split("\n"), 1):
        state, i = None, 0
        while i < len(line):
            ch = line[i]
            if state:
                if ch == BACKSLASH and i + 1 < len(line):
                    i += 2
                    continue
                if ch == state:
                    state = None
            elif ch in ('"', "'"):
                state = ch
            elif ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                break
            i += 1
        if state:
            return number
    return None


def apply_edits(text, edits):
    """Applies every edit, or raises. Returns the new text and a report."""
    report = []
    for n, edit in enumerate(edits, 1):
        if "find" not in edit or "replace" not in edit:
            raise ValueError(f"edit {n} needs both 'find' and 'replace'")
        find = build(edit["find"])
        replace = build(edit["replace"])
        hits = text.count(find)
        if hits == 0:
            raise ValueError(f"edit {n} matched nothing: {find[:60]!r}")
        if hits > 1:
            raise ValueError(f"edit {n} matched {hits} times and is ambiguous: "
                             f"{find[:60]!r}")
        text = text.replace(find, replace, 1)
        report.append(f"edit {n}: {len(find)} char(s) -> {len(replace)}")
    return text, report


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Apply JSON edits to a Pine file without escape mangling.")
    ap.add_argument("file")
    ap.add_argument("--edits", required=True,
                    help="Path to the edit list, or - to read stdin")
    ap.add_argument("--check", action="store_true",
                    help="Report what would change and write nothing")
    args = ap.parse_args(argv)

    raw = sys.stdin.read() if args.edits == "-" else \
        Path(args.edits).read_text(encoding="utf-8")
    edits = json.loads(raw)
    if isinstance(edits, dict):
        edits = [edits]

    path = Path(args.file)
    before = path.read_text(encoding="utf-8")
    try:
        after, report = apply_edits(before, edits)
    except ValueError as e:
        print(f"{path}: {e}", file=sys.stderr)
        return 1

    bad = unterminated_line(after)
    if bad is not None:
        print(f"{path}: refusing to write — line {bad} would hold a string that "
              f"never closes. Pine has no multi-line string, so that is a "
              f"compile error. Use {{\"nl\": 1}} for a line break inside a "
              f"string rather than an actual newline.", file=sys.stderr)
        return 1

    for line in report:
        print(f"  {line}")
    if args.check:
        print(f"{path}: {len(report)} edit(s) would apply, nothing written")
        return 0
    if after == before:
        print(f"{path}: unchanged")
        return 0
    path.write_text(after, encoding="utf-8")
    print(f"{path}: {len(report)} edit(s) applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
