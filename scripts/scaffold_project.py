#!/usr/bin/env python3
"""
scaffold_project.py - Create a new indicator/strategy project folder with the
standard structure used by the pine-script-cicd skill:

    <out>/<name>/
        src/<name>.pine
        version.json
        CHANGELOG.md

Usage:
    python3 scaffold_project.py --kind indicator --name my_rsi_bands --out ./indicators \
        [--title "My RSI Bands"] [--shorttitle "MRB"] [--overlay true]
"""
import argparse
import datetime
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = SCRIPT_DIR.parent / "assets" / "templates"


def slug_to_title(name):
    return name.replace("_", " ").replace("-", " ").title()


def main():
    parser = argparse.ArgumentParser(description="Scaffold a new Pine Script project folder.")
    parser.add_argument("--kind", choices=["indicator", "strategy"], required=True)
    parser.add_argument("--name", required=True, help="snake_case identifier, e.g. my_rsi_bands")
    parser.add_argument("--out", required=True, help="Output parent directory, e.g. ./indicators")
    parser.add_argument("--title", default=None, help="Display title (default: derived from --name)")
    parser.add_argument("--shorttitle", default=None, help="Short title (default: uppercase initials)")
    parser.add_argument("--overlay", default="true", choices=["true", "false"])
    args = parser.parse_args()

    title = args.title or slug_to_title(args.name)
    shorttitle = args.shorttitle or "".join(w[0] for w in title.split()).upper()[:6]

    project_dir = Path(args.out) / args.name
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    template_name = "indicator_template.pine" if args.kind == "indicator" else "strategy_template.pine"
    template_path = TEMPLATES_DIR / template_name
    template_text = template_path.read_text(encoding="utf-8")
    filled = (template_text
              .replace("{{TITLE}}", title)
              .replace("{{SHORTTITLE}}", shorttitle)
              .replace("{{OVERLAY}}", args.overlay))

    pine_path = src_dir / f"{args.name}.pine"
    if pine_path.exists():
        print(f"error: {pine_path} already exists, refusing to overwrite.")
        return 1
    pine_path.write_text(filled, encoding="utf-8")

    version_json = {
        "name": args.name,
        "version": "0.1.0",
        "pine_version": 6,
        "kind": args.kind,
    }
    (project_dir / "version.json").write_text(json.dumps(version_json, indent=2) + "\n", encoding="utf-8")

    changelog_template = (TEMPLATES_DIR / "CHANGELOG_template.md").read_text(encoding="utf-8")
    today = datetime.date.today().isoformat()
    changelog = changelog_template.replace("{{DATE}}", today).replace("{{TITLE}}", title)
    (project_dir / "CHANGELOG.md").write_text(changelog, encoding="utf-8")

    print(f"Created {args.kind} project at {project_dir}")
    print(f"  - {pine_path}")
    print(f"  - {project_dir / 'version.json'}")
    print(f"  - {project_dir / 'CHANGELOG.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
