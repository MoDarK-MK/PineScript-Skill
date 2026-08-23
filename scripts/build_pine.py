#!/usr/bin/env python3
"""
build_pine.py - Assemble one .pine file from ordered parts.

Pine has no modules and no local imports, so a growing script has nowhere to go
but down. This repo's largest file passed 1800 lines and produced a compile
error that was purely about ORDER: a declaration sat below the function that
read it, and nothing in a file that size makes that visible.

So: write parts, build one file. The parts are ordered by a manifest rather than
by filename, because Pine resolves identifiers in textual order and that order
is a real design decision — it deserves to be stated in one place instead of
encoded in prefixes like `03_`.

The generated file carries a header saying it is generated. Editing it directly
is the one way to lose work here, and `--check` exists so CI can catch a build
output that has drifted from its parts.

Layout:
    src/
      parts.json                 the manifest (ordered list of part files)
      parts/01-header.pine       whatever names you like; order comes from the manifest
      parts/…
    src/<name>.pine              the built file — generated, do not edit

Usage:
    python3 scripts/build_pine.py PROJECT            # build
    python3 scripts/build_pine.py PROJECT --check    # exit 1 if stale
    python3 scripts/build_pine.py PROJECT --split    # one-time: split an existing file
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GENERATED_BANNER = (
    "// ============================================================================\n"
    "// GENERATED FILE — DO NOT EDIT.\n"
    "// Built by scripts/build_pine.py from src/parts.json.\n"
    "// Edit the parts in src/parts/ and rebuild; edits here are lost on next build.\n"
    "// ============================================================================\n"
)

# A part boundary is a section banner, which this repo already uses everywhere.
SECTION_RE = re.compile(r'^// —————\s*(.+?)\s*$')


def display_path(path):
    """Repo-relative when it is inside the repo, absolute when it is not.

    relative_to() RAISES on a path outside the tree, so a project living
    anywhere else — a scratch directory, a test fixture, a second checkout —
    crashed the tool on its success message."""
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def project_paths(project_dir):
    project = Path(project_dir)
    if not project.is_absolute():
        project = ROOT / project
    src = project / "src"
    manifest = src / "parts.json"
    return project, src, manifest


def resolve_output(src, manifest_data, project):
    named = manifest_data.get("output")
    if named:
        return src / named
    version = project / "version.json"
    if version.exists():
        name = json.loads(version.read_text(encoding="utf-8"))["name"]
        return src / f"{name}.pine"
    candidates = [p for p in sorted(src.glob("*.pine"))]
    if len(candidates) == 1:
        return candidates[0]
    raise SystemExit("cannot determine the output file; set \"output\" in parts.json")


def build_text(src, manifest_data):
    pieces = []
    for rel in manifest_data["parts"]:
        part = src / rel
        if not part.exists():
            raise SystemExit(f"missing part: {part}")
        body = part.read_text(encoding="utf-8").rstrip("\n")
        if body:
            pieces.append(body)
    return GENERATED_BANNER + "\n" + "\n\n".join(pieces) + "\n"


def do_split(src, output, manifest):
    """One-time helper: cut an existing file into parts at its section banners.

    Deliberately refuses to overwrite an existing manifest. Splitting twice
    would shred parts that have already been edited."""
    if manifest.exists():
        raise SystemExit(f"{manifest} already exists — split is a one-time operation")
    lines = output.read_text(encoding="utf-8").splitlines()
    parts_dir = src / "parts"
    parts_dir.mkdir(exist_ok=True)

    chunks, current, title = [], [], "00-preamble"
    for line in lines:
        m = SECTION_RE.match(line)
        if m and current:
            chunks.append((title, current))
            current, title = [], m.group(1)
        elif m:
            title = m.group(1)
        current.append(line)
    if current:
        chunks.append((title, current))

    names = []
    used = set()
    for i, (title, body) in enumerate(chunks):
        slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-') or "part"
        name = f"{i:02d}-{slug}.pine"
        while name in used:
            name = f"{i:02d}-{slug}-{len(used)}.pine"
        used.add(name)
        (parts_dir / name).write_text("\n".join(body).rstrip("\n") + "\n", encoding="utf-8")
        names.append(f"parts/{name}")

    manifest.write_text(json.dumps({
        "_comment": ("Order matters: Pine resolves identifiers in textual order, so a "
                     "part may only reference what earlier parts declared. Reordering "
                     "this list is a real change."),
        "output": output.name,
        "parts": names,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"split {output.name} into {len(names)} part(s) under {parts_dir}")
    print(f"wrote {manifest}")
    print()
    print("Verify with: python3 scripts/build_pine.py <project> --check")


def main():
    parser = argparse.ArgumentParser(description="Assemble a .pine file from parts.")
    parser.add_argument("project", help="Path to the project folder")
    parser.add_argument("--check", action="store_true",
                        help="Exit 1 if the built file differs from its parts")
    parser.add_argument("--split", action="store_true",
                        help="One-time: split an existing .pine into parts at its banners")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

    project, src, manifest = project_paths(args.project)
    if not src.is_dir():
        raise SystemExit(f"no src/ directory in {project}")

    if args.split:
        candidates = sorted(src.glob("*.pine"))
        if len(candidates) != 1:
            raise SystemExit(f"expected exactly one .pine in {src}, found {len(candidates)}")
        do_split(src, candidates[0], manifest)
        return 0

    if not manifest.exists():
        print(f"{project.name}: no src/parts.json — this project is a single file "
              f"(use --split to convert it)")
        return 0

    data = json.loads(manifest.read_text(encoding="utf-8"))
    output = resolve_output(src, data, project)
    built = build_text(src, data)

    if args.check:
        current = output.read_text(encoding="utf-8") if output.exists() else ""
        if current == built:
            print(f"{display_path(output)}: up to date")
            return 0
        print(f"{display_path(output)}: OUT OF DATE")
        print(f"Run: python3 scripts/build_pine.py {args.project}")
        return 1

    output.write_text(built, encoding="utf-8")
    print(f"built {display_path(output)} from {len(data['parts'])} part(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
