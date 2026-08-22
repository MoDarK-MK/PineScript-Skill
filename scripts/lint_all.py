#!/usr/bin/env python3
"""
lint_all.py - Lint every SOURCE .pine file in the repo and summarise per file.

This exists because the shell pipeline it replaces was not trustworthy: grep
exiting non-zero inside a command substitution made a sweep report "no findings"
while a real false positive was sitting in the tree. A verification step that
can silently pass is worse than none.

Two directories are excluded on purpose:
    release/          generated bundles; gitignored, so they exist only locally
    tests/fixtures/   the compile-error corpus, which is deliberately broken

Usage:
    python3 scripts/lint_all.py              # errors and warnings fail (exit 1)
    python3 scripts/lint_all.py --no-strict  # only errors fail
    python3 scripts/lint_all.py --quiet      # print failures only
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import pine_lint  # noqa: E402

SOURCE_ROOTS = ["assets", "references", "indicators", "strategies"]
EXCLUDED_DIRS = {"release", "fixtures"}


def source_files():
    for name in SOURCE_ROOTS:
        base = ROOT / name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.pine")):
            if EXCLUDED_DIRS & set(path.parts):
                continue
            yield path


def main():
    parser = argparse.ArgumentParser(description="Lint every source .pine file.")
    parser.add_argument("--no-strict", action="store_true",
                        help="Only fail on errors; warnings are reported but tolerated")
    parser.add_argument("--quiet", action="store_true", help="Print failing files only")
    args = parser.parse_args()
    pine_lint.make_output_encoding_safe()

    strict = not args.no_strict
    files = list(source_files())
    if not files:
        print("error: no .pine source files found — is the layout right?", file=sys.stderr)
        return 1

    failing = 0
    findings = 0
    for path in files:
        result = pine_lint.lint_file(str(path), dict(pine_lint.DEFAULT_CONFIG))
        errors = result.by_severity("error")
        warnings = result.by_severity("warning")
        infos = result.by_severity("info")
        blocking = errors + (warnings if strict else [])
        label = path.relative_to(ROOT).as_posix()

        if blocking:
            failing += 1
            findings += len(blocking)
            print(f"FAIL  {label}")
            for f in sorted(blocking, key=lambda x: (x.line, x.code)):
                print(f"        line {f.line}: [{f.code}] {f.msg}")
        elif not args.quiet:
            extra = []
            if warnings:
                extra.append(f"{len(warnings)} warning")
            if infos:
                extra.append(f"{len(infos)} info")
            suffix = f"  ({', '.join(extra)})" if extra else ""
            print(f"ok    {label}{suffix}")

    print()
    mode = "strict" if strict else "errors-only"
    print(f"{len(files)} source file(s) scanned in {mode} mode — "
          f"{failing} failing, {findings} blocking finding(s)")
    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
