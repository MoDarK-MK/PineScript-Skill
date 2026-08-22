#!/usr/bin/env python3
"""
mutate_check.py - Does the test suite actually notice when a lint rule stops
working?

A passing test suite proves the tests pass. It does not prove they would fail
if the thing they test broke — and a test that cannot fail is worth nothing.
The only way to know is to break the code on purpose and check that something
goes red.

That check was done by hand in this repo several times, one rule at a time,
which means it was done once and never again. This does it for every rule.

How it works: pine_lint reads PINE_LINT_MUTATE and silently drops findings for
that one rule code. With a rule muted, the suite is re-run. If it still passes,
that rule has no test able to detect its absence — it is UNPROTECTED, and the
next refactor can silently delete it.

Usage:
    python3 mutate_check.py                 # every rule, lint-focused tests
    python3 mutate_check.py --only PINE045  # one rule
    python3 mutate_check.py --all-tests     # slower, runs the whole suite
    python3 mutate_check.py --json
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import pine_lint  # noqa: E402

# The modules that actually exercise rules. Running these instead of the whole
# suite is roughly three times faster and loses nothing: a rule with no test in
# here has no test anywhere.
LINT_TEST_MODULES = [
    "tests.test_pine_lint",
    "tests.test_untested_rules",
    "tests.test_compile_error_corpus",
    "tests.test_generate_release_bundle",
]


def run_suite(muted, all_tests):
    env = dict(os.environ)
    if muted:
        env["PINE_LINT_MUTATE"] = muted
    if all_tests:
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-q"]
    else:
        cmd = [sys.executable, "-m", "unittest", "-q", *LINT_TEST_MODULES]
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env,
                          capture_output=True, text=True)
    return proc.returncode == 0


def main():
    pine_lint.make_output_encoding_safe()
    parser = argparse.ArgumentParser(
        description="Verify the test suite detects each lint rule being disabled.")
    parser.add_argument("--only", metavar="CODE", help="Mutate just this rule")
    parser.add_argument("--all-tests", action="store_true",
                        help="Run the entire suite per rule instead of the lint modules")
    parser.add_argument("--json", action="store_true", help="Emit results as JSON")
    args = parser.parse_args()

    codes = [args.only.upper()] if args.only else sorted(pine_lint.RULES)
    unknown = [c for c in codes if c not in pine_lint.RULES]
    if unknown:
        print(f"error: unknown rule(s): {', '.join(unknown)}", file=sys.stderr)
        return 1

    # A baseline run first: if the suite is already red, every result below is
    # meaningless and reporting them would be worse than reporting nothing.
    if not run_suite(None, args.all_tests):
        print("error: the test suite fails before any mutation. Fix that first — "
              "mutation results are only meaningful against a green baseline.",
              file=sys.stderr)
        return 1

    started = time.time()
    unprotected = []
    for i, code in enumerate(codes, 1):
        detected = not run_suite(code, args.all_tests)
        if not args.json:
            mark = "detected" if detected else "UNPROTECTED"
            sev, summary = pine_lint.RULES[code]
            print(f"[{i:>2}/{len(codes)}] {code}  {mark:<12} {summary[:60]}")
        if not detected:
            unprotected.append(code)

    if args.json:
        print(json.dumps({
            "checked": codes,
            "unprotected": unprotected,
            "seconds": round(time.time() - started, 1),
        }, indent=2))
        return 1 if unprotected else 0

    print()
    print(f"{len(codes) - len(unprotected)}/{len(codes)} rule(s) protected by a test "
          f"that fails when the rule is disabled, in {time.time() - started:.0f}s.")
    if unprotected:
        print()
        print("UNPROTECTED — disabling these changes nothing the suite can see:")
        for code in unprotected:
            print(f"  {code}  {pine_lint.RULES[code][1]}")
        print()
        print("Add a test that asserts the code is reported for an offending script,")
        print("and a matching negative case. See tests/test_pine_lint.py.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
