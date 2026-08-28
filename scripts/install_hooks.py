#!/usr/bin/env python3
"""
install_hooks.py - Install the repo's git hooks.

The hook lints every staged .pine file with --strict and blocks the commit if
any of them fails, which is the same gate CI applies. Until now this existed
only as a snippet in references/repo-structure.md, so nobody actually ran it.

Usage:
    python3 scripts/install_hooks.py            # install (refuses to clobber)
    python3 scripts/install_hooks.py --force    # overwrite an existing hook
    python3 scripts/install_hooks.py --uninstall
"""
import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path

MARKER = "# pine-script-cicd hook"

HOOK_BODY = f'''#!/bin/sh
{MARKER} (pre-commit)
# Lints every staged .pine file with --strict. Bypass once with --no-verify.
#
# tests/fixtures/ is skipped on purpose: the compile-error corpus there is
# DELIBERATELY broken — each file reproduces a TradingView failure so a lint
# rule can be held in place. Linting it would block every commit that touches
# it. Same reasoning as CI pruning release/.

set -e
repo_root=$(git rev-parse --show-toplevel)
staged=$(git diff --cached --name-only --diff-filter=ACM -- '*.pine')

[ -z "$staged" ] && exit 0

status=0
for f in $staged; do
    [ -f "$repo_root/$f" ] || continue
    case "$f" in
        tests/fixtures/*) continue ;;
    esac
    if ! python "$repo_root/scripts/pine_lint.py" "$repo_root/$f" --strict; then
        status=1
    fi
done

if [ $status -ne 0 ]; then
    echo ""
    echo "pre-commit: pine_lint --strict failed on a staged .pine file."
    echo "Fix the findings, or commit with --no-verify to bypass deliberately."
fi
exit $status
'''


PREPUSH_BODY = f'''#!/bin/sh
{MARKER} (pre-push)
# Two things reading cannot catch, run at the last moment before the work
# leaves this machine. Bypass once with --no-verify.
#
#   1. EXECUTION. A script that lints clean and cannot run is the exact
#      combination this repo kept shipping. pine_run actually interprets it.
#   2. The BACKUP. indicators/ and strategies/ are gitignored, so a push is
#      precisely when they are most likely to be forgotten.

set -e
repo_root=$(git rev-parse --show-toplevel)
status=0

if [ -f "$repo_root/scripts/pine_run.py" ]; then
    for f in "$repo_root"/indicators/*/src/*.pine "$repo_root"/strategies/*/src/*.pine; do
        [ -f "$f" ] || continue
        case "$f" in
            */parts/*) continue ;;
        esac
        if ! python "$repo_root/scripts/pine_run.py" "$f" --bars 120 >/dev/null 2>&1; then
            echo "pre-push: $f does not run under the interpreter"
            status=1
        fi
    done
fi

if [ -f "$repo_root/scripts/backup_private.py" ]; then
    if ! python "$repo_root/scripts/backup_private.py" >/dev/null 2>&1; then
        echo "pre-push: the private backup could not be written"
        status=1
    fi
fi

if [ $status -ne 0 ]; then
    echo ""
    echo "pre-push: blocked. Push with --no-verify to bypass deliberately."
fi
exit $status
'''

HOOKS = {"pre-commit": HOOK_BODY, "pre-push": PREPUSH_BODY}


def hooks_dir(repo_root):
    """Respects core.hooksPath, which some setups (husky, shared configs) set."""
    try:
        configured = subprocess.run(
            ["git", "config", "--get", "core.hooksPath"],
            cwd=repo_root, capture_output=True, text=True, check=False).stdout.strip()
    except OSError:
        configured = ""
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else repo_root / path
    return repo_root / ".git" / "hooks"


def find_repo_root():
    result = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                            capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


def main():
    parser = argparse.ArgumentParser(description="Install the repo git hooks (pre-commit lint, pre-push run).")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite an existing hook that this script did not write")
    parser.add_argument("--uninstall", action="store_true", help="Remove the hooks")
    args = parser.parse_args()

    repo_root = find_repo_root()
    if repo_root is None:
        print("error: not inside a git repository.", file=sys.stderr)
        return 1

    target_dir = hooks_dir(repo_root)

    if args.uninstall:
        removed = 0
        for name in HOOKS:
            target = target_dir / name
            if not target.exists():
                continue
            if MARKER not in target.read_text(encoding="utf-8", errors="replace"):
                print(f"error: {target} was not written by this script — leaving "
                      f"it alone.", file=sys.stderr)
                return 1
            target.unlink()
            print(f"Removed {target}")
            removed += 1
        if removed == 0:
            print("No hooks installed.")
        return 0

    for name, body in HOOKS.items():
        target = target_dir / name
        if target.exists() and not args.force:
            existing = target.read_text(encoding="utf-8", errors="replace")
            if MARKER in existing:
                print(f"Hook already installed at {target} (refreshing).")
            else:
                print(f"error: {target} already exists and was not written by "
                      f"this script.\n       Re-run with --force to overwrite it.",
                      file=sys.stderr)
                return 1
        target_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8", newline="\n")
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    target = target_dir / "pre-commit"
    # git requires the hook to be executable on POSIX; harmless on Windows.
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print(f"Installed {target}")
    print("It lints staged .pine files with --strict. Bypass once with: git commit --no-verify")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
