#!/usr/bin/env python3
"""
doctor.py - Run every check this repo has, and give ONE verdict.

There are eight separate commands to run before trusting a change. Running them
one at a time means occasionally forgetting one, and the one you forget is the
one that would have caught something. This runs all of them and prints a single
table.

Checks that cannot run in the current checkout REPORT that rather than passing.
A green line for a check that never executed is the failure mode this whole
script exists to avoid.

Usage:
    python3 scripts/doctor.py
    python3 scripts/doctor.py --fast     # skip the slow mutation run
    python3 scripts/doctor.py --json
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PASS, FAIL, SKIP = "pass", "fail", "skip"
GLYPH = {PASS: "PASS", FAIL: "FAIL", SKIP: "SKIP"}


def run(cmd, cwd=ROOT):
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def py(*args):
    return [sys.executable, *args]


def pine_files():
    """Every tracked-or-not .pine that lint/format should cover."""
    out = []
    for base in ("indicators", "strategies", "libraries", "assets", "references"):
        d = ROOT / base
        if d.is_dir():
            out += [p for p in sorted(d.rglob("*.pine"))
                    if "release" not in p.parts and "fixtures" not in p.parts
                    and "parts" not in p.parts]
    return out


class Check:
    def __init__(self, name, fn, slow=False):
        self.name, self.fn, self.slow = name, fn, slow


def check_tests():
    code, out = run(py("-m", "unittest", "discover", "-s", "tests", "-t", ".", "-q"))
    ran = next((l for l in out.splitlines() if l.startswith("Ran ")), "")
    return (PASS if code == 0 else FAIL), ran or "unittest"


def check_lint():
    code, out = run(py("scripts/lint_all.py"))
    summary = next((l for l in out.splitlines() if "source file(s) scanned" in l), "")
    return (PASS if code == 0 else FAIL), summary.strip() or out.strip()[-120:]


def check_format():
    files = pine_files()
    if not files:
        return SKIP, "no .pine files in this checkout"
    code, out = run(py("scripts/pine_fmt.py", *[str(p) for p in files], "--check"))
    return (PASS if code == 0 else FAIL), out.strip().splitlines()[-1] if out.strip() else ""


def check_generated_docs():
    code, out = run(py("scripts/build_index.py", "--check"))
    return (PASS if code == 0 else FAIL), out.strip().splitlines()[0] if out.strip() else ""


def check_library_sync():
    code, out = run(py("scripts/check_library_sync.py"))
    summary = next((l for l in out.splitlines() if "drifted" in l), "")
    return (PASS if code == 0 else FAIL), summary.strip()


def check_complexity():
    script = ROOT / "scripts" / "complexity.py"
    if not script.exists():
        return SKIP, "complexity.py not present"
    code, out = run(py("scripts/complexity.py", "--check"))
    summary = next((l for l in out.splitlines() if "file(s)" in l), "")
    return (PASS if code == 0 else FAIL), summary.strip() or out.strip()[-120:]


def check_budgets():
    script = ROOT / "scripts" / "check_budget.py"
    if not script.exists():
        return SKIP, "check_budget.py not present"
    code, out = run(py("scripts/check_budget.py"))
    summary = next((l for l in out.splitlines() if "budget" in l.lower()), "")
    return (PASS if code == 0 else FAIL), summary.strip() or out.strip()[-120:]


def check_fa_reference():
    script = ROOT / "scripts" / "build_fa_reference.py"
    if not script.exists():
        return SKIP, "build_fa_reference.py not present"
    code, out = run(py("scripts/build_fa_reference.py", "--check"))
    return (PASS if code == 0 else FAIL), out.strip().splitlines()[0] if out.strip() else ""


def check_part_builds():
    """Any project built from parts must match its parts.

    A project without a manifest is a single file and passes trivially — which
    is reported as a count, so "0 built from parts" cannot look like "all good"
    when a manifest has gone missing."""
    projects, stale = 0, []
    for base in ("indicators", "strategies", "libraries"):
        d = ROOT / base
        if not d.is_dir():
            continue
        for project in sorted(d.iterdir()):
            if not (project / "src" / "parts.json").exists():
                continue
            projects += 1
            code, _out = run(py("scripts/build_pine.py", str(project), "--check"))
            if code != 0:
                stale.append(project.name)
    if projects == 0:
        return SKIP, "no projects are built from parts"
    if stale:
        return FAIL, f"stale build output: {', '.join(stale)}"
    return PASS, f"{projects} project(s) match their parts"


def check_mutation():
    code, out = run(py("scripts/mutate_check.py"))
    summary = next((l for l in out.splitlines() if "rule(s)" in l or "unprotected" in l), "")
    return (PASS if code == 0 else FAIL), summary.strip() or out.strip()[-120:]


CHECKS = [
    Check("unit tests", check_tests),
    Check("pine lint", check_lint),
    Check("pine format", check_format),
    Check("generated docs", check_generated_docs),
    Check("library sync", check_library_sync),
    Check("complexity", check_complexity),
    Check("drawing budgets", check_budgets),
    Check("persian reference", check_fa_reference),
    Check("part builds", check_part_builds),
    Check("rule mutation", check_mutation, slow=True),
]


def main():
    parser = argparse.ArgumentParser(description="Run every check and give one verdict.")
    parser.add_argument("--fast", action="store_true", help="Skip the slow mutation run")
    parser.add_argument("--skip", action="append", default=[], metavar="NAME",
                        help="Skip a named check. Repeatable. The suite uses this to "
                             "test doctor without doctor re-running the suite.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

    results = []
    for check in CHECKS:
        if check.name in args.skip:
            results.append((check.name, SKIP, "skipped by --skip", 0.0))
            continue
        if args.fast and check.slow:
            results.append((check.name, SKIP, "skipped by --fast", 0.0))
            continue
        started = time.time()
        status, detail = check.fn()
        results.append((check.name, status, detail, time.time() - started))
        if not args.json:
            print(f"  {GLYPH[status]}  {check.name:<18} {detail}"
                  f"   ({time.time() - started:.1f}s)")

    failed = [name for name, status, _d, _t in results if status == FAIL]
    skipped = [name for name, status, _d, _t in results if status == SKIP]

    if args.json:
        print(json.dumps({
            "checks": [{"name": n, "status": s, "detail": d, "seconds": round(t, 2)}
                       for n, s, d, t in results],
            "failed": failed, "skipped": skipped,
            "verdict": "fail" if failed else "pass",
        }, indent=2))
        return 1 if failed else 0

    print()
    if failed:
        print(f"FAILING — {len(failed)} check(s): {', '.join(failed)}")
    else:
        print("ALL CHECKS PASS")
    if skipped:
        # Named explicitly. A skipped check is not a passing one, and the
        # difference is invisible in a summary line that only counts failures.
        print(f"({len(skipped)} skipped: {', '.join(skipped)} — these proved nothing)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
