#!/usr/bin/env python3
"""
scaffold_project.py - Create a new indicator/strategy project folder with the
standard structure used by the pine-script-cicd skill:

    <out>/<name>/
        src/<name>.pine
        version.json
        CHANGELOG.md

Usage:
    python3 scaffold_project.py --kind indicator --name my_rsi_bands --out ./indicators \\
        [--title "My RSI Bands"] [--shorttitle "MRB"] [--overlay true] \\
        [--profile full|lite|oscillator]

Profiles (indicator only):
    full        Full template: dashboard, test block, 4-mode theme system (default)
    lite        Lightweight: no dashboard, no tests — clean minimal structure
    oscillator  Sub-pane panel: histogram, signal line, hlines, gradient fill
"""
import argparse
import datetime
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = SCRIPT_DIR.parent / "assets" / "templates"

INDICATOR_TEMPLATES = {
    "full":        "indicator_template.pine",
    "lite":        "indicator_lite_template.pine",
    "oscillator":  "indicator_oscillator_template.pine",
}

STRATEGY_TEMPLATES = {
    "full":       "strategy_template.pine",
    # Strategies only have one profile: they always need risk modules.
    "lite":       "strategy_template.pine",
    "oscillator": "strategy_template.pine",
}


def slug_to_title(name):
    return name.replace("_", " ").replace("-", " ").title()


def main():
    parser = argparse.ArgumentParser(
        description="Scaffold a new Pine Script project folder.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage:")[0].strip(),
    )
    parser.add_argument("--kind", choices=["indicator", "strategy"], required=True,
                        help="indicator or strategy")
    parser.add_argument("--name", required=True,
                        help="snake_case identifier, e.g. my_rsi_bands")
    parser.add_argument("--out", required=True,
                        help="Output parent directory, e.g. ./indicators")
    parser.add_argument("--title", default=None,
                        help="Display title (default: derived from --name)")
    parser.add_argument("--shorttitle", default=None,
                        help="Short title (default: uppercase initials, max 6 chars)")
    parser.add_argument("--overlay", default="true", choices=["true", "false"],
                        help="overlay= parameter for indicator() (default: true). "
                             "Ignored for oscillator profile (always false).")
    parser.add_argument("--profile",
                        choices=list(INDICATOR_TEMPLATES), default="full",
                        help=(
                            "full (default): dashboard + test block + 4-mode theme. "
                            "lite: minimal overlay, no dashboard. "
                            "oscillator: sub-pane panel with hlines, histogram, "
                            "signal line."
                        ))
    args = parser.parse_args()

    title = args.title or slug_to_title(args.name)
    shorttitle = args.shorttitle or "".join(w[0] for w in title.split()).upper()[:6]

    # Oscillator profile forces overlay=false — it makes no sense on the price pane.
    overlay = "false" if args.profile == "oscillator" else args.overlay

    project_dir = Path(args.out) / args.name
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    if args.kind == "indicator":
        template_name = INDICATOR_TEMPLATES[args.profile]
    else:
        if args.profile != "full":
            print(
                f"note: strategies always use the full template "
                f"(--profile {args.profile!r} ignored)."
            )
        template_name = STRATEGY_TEMPLATES[args.profile]

    template_path = TEMPLATES_DIR / template_name
    if not template_path.exists():
        print(f"error: template not found: {template_path}")
        return 1

    template_text = template_path.read_text(encoding="utf-8")
    filled = (template_text
              .replace("{{TITLE}}", title)
              .replace("{{SHORTTITLE}}", shorttitle)
              .replace("{{OVERLAY}}", overlay))

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
        "profile": args.profile,
    }
    (project_dir / "version.json").write_text(
        json.dumps(version_json, indent=2) + "\n", encoding="utf-8"
    )

    changelog_template = (TEMPLATES_DIR / "CHANGELOG_template.md").read_text(encoding="utf-8")
    today = datetime.date.today().isoformat()
    changelog = changelog_template.replace("{{DATE}}", today).replace("{{TITLE}}", title)
    (project_dir / "CHANGELOG.md").write_text(changelog, encoding="utf-8")

    profile_label = {
        "full":       "full (dashboard + theme + tests)",
        "lite":       "lite (minimal overlay)",
        "oscillator": "oscillator (sub-pane panel)",
    }.get(args.profile, args.profile)

    print(f"Created {args.kind} project [{profile_label}] at {project_dir}")
    print(f"  Pine:      {pine_path}")
    print(f"  Version:   {project_dir / 'version.json'}")
    print(f"  Changelog: {project_dir / 'CHANGELOG.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
