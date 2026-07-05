#!/usr/bin/env python3
"""
bump_version.py - Bump semantic version in a project's version.json and stamp
the changelog: renames the "## [Unreleased]" section to "## [x.y.z] - YYYY-MM-DD"
and inserts a fresh empty "## [Unreleased]" section above it.

Usage:
    python3 bump_version.py path/to/project --bump patch --note "Fixed off-by-one bug"
    python3 bump_version.py path/to/project --bump minor --note "Added smoothing input"
    python3 bump_version.py path/to/project --bump major --note "Changed default alert format"
"""
import argparse
import datetime
import json
import re
from pathlib import Path


def bump(version_str, part):
    major, minor, patch = (int(x) for x in version_str.split("."))
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    elif part == "patch":
        patch += 1
    else:
        raise ValueError(f"Unknown bump part: {part}")
    return f"{major}.{minor}.{patch}"


def update_changelog(changelog_path, new_version, note):
    today = datetime.date.today().isoformat()
    text = changelog_path.read_text(encoding="utf-8")

    if "## [Unreleased]" not in text:
        # No unreleased section — just prepend a new one under the H1 title.
        text = re.sub(r"(^# .*\n)", rf"\1\n## [Unreleased]\n- (nothing yet)\n\n", text, count=1)

    note_line = f"- {note}" if note else "- (no notes provided)"
    new_section_header = f"## [{new_version}] - {today}"

    # Replace the Unreleased section: move its bullet(s) under the new version
    # header, then insert a fresh empty Unreleased section above it.
    pattern = re.compile(r"## \[Unreleased\]\n(.*?)(?=\n## |\Z)", re.DOTALL)
    m = pattern.search(text)
    if not m:
        raise RuntimeError("Could not locate '## [Unreleased]' section in changelog.")

    existing_notes = m.group(1).strip()
    if existing_notes and existing_notes != "- (nothing yet)":
        released_body = existing_notes + "\n" + note_line
    else:
        released_body = note_line

    replacement = f"## [Unreleased]\n- (nothing yet)\n\n{new_section_header}\n{released_body}\n"
    text = text[:m.start()] + replacement + text[m.end():]
    changelog_path.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Bump version and stamp changelog.")
    parser.add_argument("project_dir", help="Path to the project folder (contains version.json, CHANGELOG.md)")
    parser.add_argument("--bump", choices=["major", "minor", "patch"], required=True)
    parser.add_argument("--note", default="", help="One-line changelog note for this release")
    args = parser.parse_args()

    project_dir = Path(args.project_dir)
    version_path = project_dir / "version.json"
    changelog_path = project_dir / "CHANGELOG.md"

    if not version_path.exists():
        print(f"error: {version_path} not found.")
        return 1
    if not changelog_path.exists():
        print(f"error: {changelog_path} not found.")
        return 1

    data = json.loads(version_path.read_text(encoding="utf-8"))
    old_version = data["version"]
    new_version = bump(old_version, args.bump)
    data["version"] = new_version
    version_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    update_changelog(changelog_path, new_version, args.note)

    print(f"Bumped {data.get('name', project_dir.name)}: {old_version} -> {new_version}")
    print(f"Updated {changelog_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
