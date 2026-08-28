"""Version-control the work that is deliberately kept out of GitHub.

`indicators/` and `strategies/` are in .gitignore on purpose - they are not for
publishing. The consequence nobody chose is that they had no version control and
no backup at all: one mistaken delete and every indicator in this repo is gone,
with no history to recover a working version from.

This gives them their own git repository, OUTSIDE the GitHub repo so it can
never be pushed by accident, and commits a snapshot on demand. It is a real
repository, not a copy: `git log` in the backup shows every snapshot and `git
diff` between any two of them works.

    python3 scripts/backup_private.py            # snapshot now
    python3 scripts/backup_private.py --status   # what is stored, and when
    python3 scripts/backup_private.py --restore  # print how to get files back

The default location is a sibling of this repo. It is deliberately NOT inside
it: a backup that lives in the thing it is backing up is not a backup.
"""
import argparse
import datetime
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = ROOT.parent / f"{ROOT.name}-private-backup"
# What is worth keeping. Everything here is gitignored in the main repo.
SOURCES = ("indicators", "strategies")
# Build output is reproducible from src/, so it is not worth storing - except
# the released .pine, which is what was actually handed over and is the one
# artefact that cannot be regenerated once the source moves on.
SKIP_DIRS = {"__pycache__", ".git"}


def run_git(target, *args, check=True):
    return subprocess.run(("git",) + args, cwd=target, check=check,
                          capture_output=True, text=True)


def ensure_repo(target):
    """Creates the backup repository if it is not there yet."""
    target.mkdir(parents=True, exist_ok=True)
    if not (target / ".git").exists():
        run_git(target, "init", "-q")
        run_git(target, "config", "user.name", "pine-backup", check=False)
        run_git(target, "config", "user.email", "backup@localhost", check=False)
        # Store bytes exactly as found. With autocrlf on, `git show` hands back
        # LF for a file saved with CRLF - the content is intact but a recovered
        # file is not byte-identical to the one that was lost, and a backup you
        # have to think about is one you cannot trust in a hurry.
        run_git(target, "config", "core.autocrlf", "false", check=False)
        (target / "README.md").write_text(
            "# Private Pine backup\n\n"
            "Snapshots of `indicators/` and `strategies/`, which are gitignored "
            "in the main repository on purpose and therefore had no history of "
            "their own.\n\n"
            "This repository has NO remote and is not meant to get one. Written "
            "by `scripts/backup_private.py`.\n\n"
            "To recover a file:\n\n"
            "    git -C <this dir> log --oneline\n"
            "    git -C <this dir> show <commit>:indicators/<name>/src/<name>.pine\n",
            encoding="utf-8")
        return True
    return False


def mirror(source, dest):
    """Copies a tree, replacing whatever was there. Returns the file count."""
    if dest.exists():
        shutil.rmtree(dest)
    if not source.exists():
        return 0
    count = 0
    for item in source.rglob("*"):
        if any(part in SKIP_DIRS for part in item.parts):
            continue
        rel = item.relative_to(source)
        out = dest / rel
        if item.is_dir():
            out.mkdir(parents=True, exist_ok=True)
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, out)
            count += 1
    return count


def source_commit():
    try:
        r = subprocess.run(("git", "rev-parse", "--short", "HEAD"), cwd=ROOT,
                           check=True, capture_output=True, text=True)
        return r.stdout.strip()
    except Exception:
        return "unknown"


def snapshot(target):
    created = ensure_repo(target)
    total = 0
    for name in SOURCES:
        total += mirror(ROOT / name, target / name)

    run_git(target, "add", "-A")
    status = run_git(target, "status", "--porcelain")
    if not status.stdout.strip():
        print(f"{target}: already up to date ({total} file(s), nothing changed)")
        return 0

    changed = len(status.stdout.strip().splitlines())
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    message = f"snapshot {stamp} (skill @ {source_commit()})"
    run_git(target, "commit", "-q", "-m", message)
    head = run_git(target, "rev-parse", "--short", "HEAD").stdout.strip()
    if created:
        print(f"created backup repository at {target}")
    print(f"{target}: committed {head} — {changed} path(s) changed, "
          f"{total} file(s) stored")
    return 0


def show_status(target):
    if not (target / ".git").exists():
        print(f"no backup repository at {target}")
        print("run: python3 scripts/backup_private.py")
        return 1
    log = run_git(target, "log", "--oneline", "-8", check=False).stdout.strip()
    files = sum(1 for p in target.rglob("*")
                if p.is_file() and ".git" not in p.parts)
    print(f"backup: {target}")
    print(f"files stored: {files}")
    dirty = run_git(target, "status", "--porcelain", check=False).stdout.strip()
    print("uncommitted changes in the backup: "
          + (f"{len(dirty.splitlines())} path(s)" if dirty else "none"))
    print("\nrecent snapshots:")
    print(log or "  (none yet)")
    return 0


def show_restore(target):
    print(f"The backup is a git repository at {target}.")
    print()
    print("  # what snapshots exist")
    print(f"  git -C \"{target}\" log --oneline")
    print()
    print("  # read one file as it was at a snapshot")
    print(f"  git -C \"{target}\" show <commit>:indicators/<name>/src/<name>.pine")
    print()
    print("  # what changed between two snapshots")
    print(f"  git -C \"{target}\" diff <older> <newer> -- indicators/")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Snapshot the gitignored indicators and strategies.")
    ap.add_argument("--target", default=str(DEFAULT_TARGET),
                    help="Backup repository location (default: a sibling of this repo)")
    ap.add_argument("--status", action="store_true", help="Report what is stored")
    ap.add_argument("--restore", action="store_true",
                    help="Print the commands that get a file back")
    args = ap.parse_args(argv)
    target = Path(args.target).resolve()

    if target == ROOT or ROOT in target.parents:
        print("refusing: the backup must not live inside the repository it "
              "backs up.", file=sys.stderr)
        return 2
    if args.status:
        return show_status(target)
    if args.restore:
        return show_restore(target)
    return snapshot(target)


if __name__ == "__main__":
    raise SystemExit(main())
