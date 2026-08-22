#!/usr/bin/env python3
"""
new_rule.py - Scaffold a new pine_lint rule across every place it has to appear.

Adding a rule by hand touches the catalog, a check function, the lint_file call
list, references/lint-rules.md, and (until the counts became generated) several
prose claims. Missing one of those is exactly how this repo ended up with
mismatched rule counts more than once.

This picks the next free code, writes a stub in each place, and tells you what
to fill in. It never invents the detection logic — that is the part a human
has to think about.

Usage:
    python3 scripts/new_rule.py --severity error \\
        --summary "strategy.exit() with no level" \\
        --title "strategy.exit() without a level" \\
        --check check_exit_has_level

    python3 scripts/new_rule.py --next     # just print the next free code
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINTER = ROOT / "scripts" / "pine_lint.py"
CATALOG = ROOT / "references" / "lint-rules.md"

SEVERITIES = ("error", "warning", "info")


def existing_codes():
    text = LINTER.read_text(encoding="utf-8")
    return sorted(int(m) for m in re.findall(r'"PINE(\d{3})":', text))


def next_code():
    codes = existing_codes()
    return f"PINE{codes[-1] + 1:03d}"


def insert_catalog_entry(code, severity, summary):
    text = LINTER.read_text(encoding="utf-8")
    codes = existing_codes()
    last = f'"PINE{codes[-1]:03d}": ('
    idx = text.index(last)
    line_end = text.index("\n", idx) + 1
    entry = f'    "{code}": ("{severity}", "{summary}"),\n'
    LINTER.write_text(text[:line_end] + entry + text[line_end:], encoding="utf-8")


def insert_check_stub(code, check_name, summary):
    text = LINTER.read_text(encoding="utf-8")
    anchor = "def check_transp_removed(statements, result):"
    stub = f'''def {check_name}(lines, result):
    """{code} — {summary}

    TODO: implement the detection. Useful helpers already in this file:
      strip_strings_and_comments / strip_comments_only  — safe text per line
      build_logical_statements                          — wrapped calls joined
      statements_calling(statements, "func(")           — call sites + arg text
      split_top_level_args / named_arg / positional_args
      iter_function_bodies(lines)                       — user functions
      indent_width(raw_line)                            — scope depth
    """
    for i, raw in enumerate(lines):
        line = strip_strings_and_comments(raw)
        if False:      # TODO: replace with the real condition
            result.add(i + 1, "{code}",
                        "TODO: explain what is wrong, why it matters, and what to "
                        "do instead. Messages here are read by traders, not just "
                        "developers.")
            return


'''
    idx = text.index(anchor)
    LINTER.write_text(text[:idx] + stub + text[idx:], encoding="utf-8")


def insert_call(check_name):
    text = LINTER.read_text(encoding="utf-8")
    anchor = "    check_request_count(statements, result, cfg)"
    if anchor not in text:
        anchor = "    check_na_comparison(lines, result)"
    idx = text.index(anchor)
    line_end = text.index("\n", idx) + 1
    LINTER.write_text(text[:line_end] + f"    {check_name}(lines, result)\n" + text[line_end:],
                      encoding="utf-8")


def append_catalog_doc(code, severity, title):
    text = CATALOG.read_text(encoding="utf-8")
    section = f'''

### {code} — {severity} — {title}
TODO: describe the defect, then show a bad and a good example.
```pinescript
// bad
```
```pinescript
// good
```
'''
    CATALOG.write_text(text.rstrip("\n") + section, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Scaffold a new pine_lint rule.")
    parser.add_argument("--next", action="store_true", help="Print the next free code and exit")
    parser.add_argument("--severity", choices=SEVERITIES)
    parser.add_argument("--summary", help="One-line summary for --list-rules")
    parser.add_argument("--title", help="Heading text for references/lint-rules.md")
    parser.add_argument("--check", help="Name of the check function, e.g. check_my_rule")
    args = parser.parse_args()

    if args.next:
        print(next_code())
        return 0

    missing = [n for n in ("severity", "summary", "title", "check")
               if not getattr(args, n)]
    if missing:
        parser.error("required unless --next: " + ", ".join("--" + m for m in missing))

    if not re.fullmatch(r'check_[a-z0-9_]+', args.check):
        parser.error("--check must look like check_something_lowercase")

    code = next_code()
    insert_catalog_entry(code, args.severity, args.summary)
    insert_check_stub(code, args.check, args.summary)
    insert_call(args.check)
    append_catalog_doc(code, args.severity, args.title)

    print(f"Scaffolded {code} ({args.severity})")
    print()
    print("Now do the three things this script cannot do for you:")
    print(f"  1. Implement {args.check}() in scripts/pine_lint.py")
    print(f"  2. Fill in the bad/good examples for {code} in references/lint-rules.md")
    print(f"  3. Add a positive AND a negative test to tests/test_pine_lint.py")
    print()
    print("Then run: python -m unittest discover -s tests -t .")
    print("The consistency tests will fail until the docs and counts line up,")
    print("which is the point — they are the reason counts stopped drifting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
