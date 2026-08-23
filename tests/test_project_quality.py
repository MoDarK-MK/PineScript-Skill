"""Quality gates that apply to every shipped project, not to one script.

These exist because "we should remember to do that" is not a mechanism. Each
one here replaced a convention that was written down and then drifted.
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

from tests.helpers import REPO_ROOT, SCRIPTS_DIR

import input_inventory
import pine_fmt

# Groups every script has and nobody needs explained. "Theme / Bullish Color /
# Bearish Color" and "Test Mode" describe themselves; demanding prose for them
# would train people to write filler, which is worse than a gap.
SELF_EVIDENT_GROUPS = {"Appearance", "Debug/Test"}


def project_dirs():
    for parent in ("indicators", "strategies", "libraries"):
        base = REPO_ROOT / parent
        if base.is_dir():
            for child in sorted(base.iterdir()):
                if (child / "version.json").exists():
                    yield child


def source_files():
    """Every .pine file the repo authors, excluding generated release copies
    and the deliberately-broken compile-error fixtures."""
    for path in sorted(REPO_ROOT.rglob("*.pine")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if "/release/" in rel or rel.startswith("tests/fixtures/"):
            continue
        yield path


class TestInputDocumentation(unittest.TestCase):
    def test_every_settings_group_explains_itself(self):
        """A published script's settings panel IS its user interface. A section
        with no explanation anywhere in it has to be reverse-engineered from
        source the reader cannot see."""
        gaps = []
        for project in project_dirs():
            source = input_inventory.resolve_source(project)
            inputs = input_inventory.extract_inputs(source.read_text(encoding="utf-8"))
            groups = {}
            for item in inputs:
                groups.setdefault(item["group"], []).append(item)
            for group, members in groups.items():
                if group in SELF_EVIDENT_GROUPS:
                    continue
                if not any(m["tooltip"] for m in members):
                    gaps.append(f"{project.name}: group '{group}' has no tooltip on any "
                                f"of its {len(members)} input(s)")
        self.assertEqual([], gaps, msg="\n".join(gaps))

    def test_every_input_has_a_title(self):
        """An EMPTY title is fine when the input shares an inline row with a
        sibling carrying the label — that is how a paired colour picker is meant
        to look. A title that is absent entirely is not."""
        untitled = []
        for project in project_dirs():
            source = input_inventory.resolve_source(project)
            for item in input_inventory.extract_inputs(source.read_text(encoding="utf-8")):
                if item["title"] is None and item["inline"] is None:
                    untitled.append(f"{project.name}:{item['line']}: {item['variable']}")
        self.assertEqual([], untitled, msg="\n".join(untitled))

    def test_inventory_resolves_group_constants(self):
        """group=SW_GROUP must render as the heading the user sees, not as the
        constant's name — the first version of this tool shipped the latter."""
        source = REPO_ROOT / "tests" / "fixtures" / "inputs_sample.pine"
        groups = {i["group"] for i in
                  input_inventory.extract_inputs(source.read_text(encoding="utf-8"))}
        self.assertIn("Swing Detection", groups)
        self.assertNotIn("SW_GROUP", groups)

    def test_inventory_joins_concatenated_tooltip_strings(self):
        """Pine has no multi-line string, so every long tooltip is written as
        "part one " + "part two". Rendering the expression verbatim is what the
        first version did, and the tables were unreadable."""
        source = REPO_ROOT / "tests" / "fixtures" / "inputs_sample.pine"
        tips = [i["tooltip"] for i in
                input_inventory.extract_inputs(source.read_text(encoding="utf-8"))
                if i["tooltip"]]
        self.assertTrue(tips)
        for tip in tips:
            self.assertNotIn('" +', tip)
            self.assertNotIn('"', tip)

    def test_inventory_escapes_pipes_in_markdown(self):
        """A title containing "|" would silently split its table row."""
        rendered = input_inventory.render_markdown(
            [{"variable": "x", "type": "bool", "title": "Sell | Buy", "default": "true",
              "group": "G", "inline": None, "minval": None, "maxval": None,
              "step": None, "options": None, "tooltip": None, "line": 1}],
            "demo")
        row = [l for l in rendered.splitlines() if "Sell" in l][0]
        self.assertEqual(5, row.count("|") - row.count("\\|") - 1)


class TestFormatting(unittest.TestCase):
    def test_every_source_file_is_formatted(self):
        unformatted = []
        for path in source_files():
            text = path.read_text(encoding="utf-8")
            if pine_fmt.format_text(text) != text:
                unformatted.append(path.relative_to(REPO_ROOT).as_posix())
        self.assertEqual([], unformatted,
                         msg="run: python3 scripts/pine_fmt.py " + " ".join(unformatted))

    def test_formatter_preserves_string_contents(self):
        src = 'x = "a,b  ==  c"\n'
        self.assertEqual(src, pine_fmt.format_text(src))

    def test_formatter_preserves_generic_type_brackets(self):
        src = "d = array.new<float>(5, 0.0)\n"
        self.assertEqual(src, pine_fmt.format_text(src))

    def test_formatter_preserves_alignment_columns(self):
        """This repo aligns `=` into columns across a block of inputs. A
        formatter that collapses runs of spaces destroys every one of them
        while believing it is tidying up — an earlier draft of pine_fmt did
        exactly that."""
        src = "int   MAX_SCORE         = 5\nstring THEME_DARK       = \"Dark\"\n"
        self.assertEqual(src, pine_fmt.format_text(src))

    def test_formatter_fixes_what_it_claims_to(self):
        src = "a = 1   \nif a==1\n\tb = ta.sma(close,10)\n"
        out = pine_fmt.format_text(src)
        self.assertIn("if a == 1", out)
        self.assertIn("ta.sma(close, 10)", out)
        self.assertNotIn("\t", out)
        self.assertNotIn("   \n", out)

    def test_formatter_never_changes_indentation_depth(self):
        src = "if close > open\n    x = 1\n     y = 2\n"
        self.assertEqual(src, pine_fmt.format_text(src))

    def test_check_mode_exits_1_on_unformatted_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            pine = Path(td) / "messy.pine"
            pine.write_text("a = 1   \n", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "pine_fmt.py"), str(pine), "--check"],
                capture_output=True, text=True)
            self.assertEqual(1, proc.returncode)
            self.assertEqual("a = 1   \n", pine.read_text(encoding="utf-8"))


class TestReleaseBundleInputs(unittest.TestCase):
    def test_bundles_carry_an_inputs_table(self):
        missing = []
        for project in project_dirs():
            inputs_md = project / "release" / "INPUTS.md"
            if not inputs_md.exists():
                missing.append(project.name)
        self.assertEqual([], missing,
                         msg="regenerate with scripts/generate_release_bundle.py: " + str(missing))

    def test_inputs_table_matches_the_current_source(self):
        stale = []
        for project in project_dirs():
            inputs_md = project / "release" / "INPUTS.md"
            if not inputs_md.exists():
                continue
            name = json.loads((project / "version.json").read_text(encoding="utf-8"))["name"]
            source = input_inventory.resolve_source(project)
            expected = input_inventory.render_markdown(
                input_inventory.extract_inputs(source.read_text(encoding="utf-8")), name)
            if inputs_md.read_text(encoding="utf-8") != expected:
                stale.append(project.name)
        self.assertEqual([], stale,
                         msg="INPUTS.md is out of date for: " + str(stale))


if __name__ == "__main__":
    unittest.main()
