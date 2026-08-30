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


def check_interpreter():
    """Runs every project through the Pine interpreter.

    Not a lint pass — actual EXECUTION. A script that lints clean and cannot
    run is exactly the combination this repo kept shipping."""
    script = ROOT / "scripts" / "pine_run.py"
    if not script.exists():
        return SKIP, "pine_run.py not present"
    targets = []
    for base in ("indicators", "strategies", "libraries"):
        d = ROOT / base
        if not d.is_dir():
            continue
        for project in sorted(d.iterdir()):
            src = project / "src"
            if not src.is_dir():
                continue
            found = [f for f in sorted(src.glob("*.pine"))]
            if len(found) == 1:
                targets.append(found[0])
    if not targets:
        return SKIP, "no projects to run"
    failed = []
    for path in targets:
        code, out = run(py("scripts/pine_run.py", str(path), "--bars", "150"))
        if code != 0:
            failed.append(f"{path.parent.parent.name}: {out.strip().splitlines()[-1][:70]}")
    if failed:
        return FAIL, "; ".join(failed)
    return PASS, f"{len(targets)} script(s) executed over 150 bars"


def check_release_bundles():
    """Is every release bundle current with the source it was built from?

    A bundle is only rebuilt when someone rebuilds it, so a change to the
    comment-stripping - or to anything else in the pipeline - reaches only the
    projects that happen to be regenerated afterwards. Three bundles here still
    carried 492 lines of comment long after the release stopped shipping any,
    and nothing said so because nothing was looking."""
    import strip_comments
    stale, checked = [], 0
    for base in ("indicators", "strategies"):
        d = ROOT / base
        if not d.is_dir():
            continue
        for project in sorted(d.iterdir()):
            src = project / "src" / f"{project.name}.pine"
            rel = project / "release" / f"{project.name}.pine"
            if not (src.exists() and rel.exists()):
                continue
            checked += 1
            want = strip_comments.strip_pine_comments(
                src.read_text(encoding="utf-8"))
            have = rel.read_text(encoding="utf-8")
            code = lambda s: [l for l in s.splitlines()
                              if l.strip() and not l.strip().startswith("//")]
            if code(want) != code(have):
                stale.append(project.name)
    if checked == 0:
        return SKIP, "no release bundles to check"
    if stale:
        return FAIL, ("stale bundle(s): " + ", ".join(stale) +
                      " — run scripts/generate_release_bundle.py")
    return PASS, f"{checked} bundle(s) match their source"


def check_private_backup():
    """Is the gitignored work backed up, and is the backup current?

    `indicators/` and `strategies/` are excluded from git on purpose, which
    also excluded them from having any history at all. This is the one check
    here whose failure mode is losing work rather than shipping a fault, so it
    reports STALE as a failure rather than a note."""
    script = ROOT / "scripts" / "backup_private.py"
    if not script.exists():
        return SKIP, "backup_private.py not present"
    sources = [ROOT / n for n in ("indicators", "strategies")]
    if not any(s.is_dir() for s in sources):
        return SKIP, "nothing private to back up"
    code, out = run(py("scripts/backup_private.py", "--status"))
    if code != 0:
        return FAIL, "no backup exists — run scripts/backup_private.py"
    stored = next((l for l in out.splitlines() if l.startswith("files stored")), "")
    dirty = next((l for l in out.splitlines()
                  if l.startswith("uncommitted changes")), "")
    # The snapshot is only refreshed when the script runs, so fewer stored
    # files than live ones means it is BEHIND, not broken. The backup carries
    # its own README, so it holds one more file than the sources do.
    live = sum(1 for base in sources if base.is_dir()
               for f in base.rglob("*") if f.is_file()
               and "__pycache__" not in f.parts)
    saved = next((int(l.split(":")[1]) for l in out.splitlines()
                  if l.startswith("files stored")), 0)
    if saved - 1 < live:
        return FAIL, (f"backup is behind: {saved - 1} file(s) stored against "
                      f"{live} live — run scripts/backup_private.py")
    return PASS, f"{stored.split(':')[1].strip()} file(s) stored, {dirty.split(':')[1].strip()} pending"


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
    Check("interpreter run", check_interpreter),
    Check("release bundles", check_release_bundles),
    Check("private backup", check_private_backup),
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
