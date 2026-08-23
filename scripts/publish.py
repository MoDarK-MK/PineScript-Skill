#!/usr/bin/env python3
"""
publish.py - Put a release on the clipboard, with the release notes beside it.

The last step of every release is the same: open release/<name>.pine, select
all, copy, switch to the Pine Editor, paste. Then open PUBLISH_DESCRIPTION.md
and copy that too. It is four manual steps that can go wrong in one specific
way — pasting the SOURCE file instead of the RELEASE file, which is the one
that has not been through the gate.

This copies the right file and says which one it copied.

TradingView's own update-notes box takes plain text, not Markdown, so
--notes renders the changelog entry for the current version in the shape that
box expects instead of the shape a README expects.

Usage:
    python3 scripts/publish.py PROJECT              # release .pine -> clipboard
    python3 scripts/publish.py PROJECT --notes      # release notes -> clipboard
    python3 scripts/publish.py PROJECT --notes --print
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def to_clipboard(text):
    """Returns True if the text reached a clipboard.

    Never silently fails: a script that claims to have copied something and has
    not is worse than one that admits it cannot."""
    attempts = []
    if sys.platform == "win32":
        attempts = [["clip"]]
    elif sys.platform == "darwin":
        attempts = [["pbcopy"]]
    else:
        attempts = [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "-ib"]]
    for cmd in attempts:
        try:
            proc = subprocess.run(cmd, input=text.encode("utf-8"), check=False)
            if proc.returncode == 0:
                return True
        except (OSError, FileNotFoundError):
            continue
    return False


def project_name(project):
    version_file = project / "version.json"
    if version_file.exists():
        data = json.loads(version_file.read_text(encoding="utf-8"))
        return data["name"], data["version"]
    return project.name, None


def render_notes(project, version):
    """The newest CHANGELOG entry, flattened for TradingView's notes box.

    That box is plain text: Markdown headings, links and backticks all render
    literally, so leaving them in produces a release note full of punctuation."""
    changelog = project / "CHANGELOG.md"
    if not changelog.exists():
        return None
    text = changelog.read_text(encoding="utf-8")
    pattern = re.compile(r'^## \[' + re.escape(version) + r'\][^\n]*\n(.*?)(?=^## \[|\Z)',
                         re.MULTILINE | re.DOTALL)
    m = pattern.search(text)
    if not m:
        return None
    body = m.group(1).strip("\n")
    out = []
    for line in body.splitlines():
        line = line.rstrip()
        if not line.strip():
            out.append("")
            continue
        if line.startswith("### "):
            out.append(line[4:].upper())
            continue
        line = re.sub(r'`([^`]*)`', r'\1', line)
        line = re.sub(r'\*\*([^*]*)\*\*', r'\1', line)
        line = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', line)
        if line.lstrip().startswith("- "):
            line = line.lstrip()[2:]
            line = "- " + line
        out.append(line)
    while out and not out[0].strip():
        out.pop(0)
    return "\n".join(out).strip() + "\n"


def main():
    parser = argparse.ArgumentParser(description="Copy a release to the clipboard.")
    parser.add_argument("project")
    parser.add_argument("--notes", action="store_true",
                        help="Copy the release notes instead of the script")
    parser.add_argument("--print", dest="show", action="store_true",
                        help="Print to stdout as well")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

    project = Path(args.project)
    if not project.is_absolute():
        project = ROOT / project
    if not project.is_dir():
        raise SystemExit(f"no such project: {project}")

    name, version = project_name(project)

    if args.notes:
        if not version:
            raise SystemExit("no version.json, so there is no version to find notes for")
        payload = render_notes(project, version)
        if payload is None:
            raise SystemExit(f"no CHANGELOG entry for {version}")
        label = f"release notes for {name} v{version}"
    else:
        source = project / "release" / f"{name}.pine"
        if not source.exists():
            raise SystemExit(
                f"no release bundle at {source}.\n"
                f"Run: python3 scripts/generate_release_bundle.py {args.project}")
        payload = source.read_text(encoding="utf-8")
        label = f"{source.relative_to(ROOT)} ({len(payload.splitlines())} lines)"

    if args.show:
        print(payload)

    if to_clipboard(payload):
        print(f"copied to clipboard: {label}")
        if not args.notes:
            print("This is the RELEASE file — the one that passed the gate, not src/.")
        return 0

    print(f"could not reach a clipboard on this system — nothing was copied.",
          file=sys.stderr)
    print(f"The content is at: {project / 'release' / (name + '.pine')}"
          if not args.notes else "Re-run with --print to see the notes.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
