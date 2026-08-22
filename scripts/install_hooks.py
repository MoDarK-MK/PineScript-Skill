#!/usr/bin/env python3
"""
install_hooks.py - Install the repo's git pre-commit hook.

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

HOOK_NAME = "pre-commit"
MARKER = "# pine-script-cicd pre-commit hook"

HOOK_BODY = f'''#!/bin/sh
{MARKER}
# Lints every staged .pine file with --strict. Bypass once with --no-verify.

set -e
repo_root=$(git rev-parse --show-toplevel)
staged=$(git diff --cached --name-only --diff-filter=ACM -- '*.pine')

[ -z "$staged" ] && exit 0

status=0
for f in $staged; do
    [ -f "$repo_root/$f" ] || continue
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
    parser = argparse.ArgumentParser(description="Install the pre-commit lint hook.")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite an existing hook that this script did not write")
    parser.add_argument("--uninstall", action="store_true", help="Remove the hook")
    args = parser.parse_args()

    repo_root = find_repo_root()
    if repo_root is None:
        print("error: not inside a git repository.", file=sys.stderr)
        return 1

    target_dir = hooks_dir(repo_root)
    target = target_dir / HOOK_NAME

    if args.uninstall:
        if not target.exists():
            print(f"No {HOOK_NAME} hook installed.")
            return 0
        if MARKER not in target.read_text(encoding="utf-8", errors="replace"):
            print(f"error: {target} was not written by this script — leaving it alone.",
                  file=sys.stderr)
            return 1
        target.unlink()
        print(f"Removed {target}")
        return 0

    if target.exists() and not args.force:
        existing = target.read_text(encoding="utf-8", errors="replace")
        if MARKER in existing:
            print(f"Hook already installed at {target} (refreshing).")
        else:
            print(f"error: {target} already exists and was not written by this script.\n"
                  f"       Re-run with --force to overwrite it.", file=sys.stderr)
            return 1

    target_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(HOOK_BODY, encoding="utf-8", newline="\n")
    # git requires the hook to be executable on POSIX; harmless on Windows.
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print(f"Installed {target}")
    print("It lints staged .pine files with --strict. Bypass once with: git commit --no-verify")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
