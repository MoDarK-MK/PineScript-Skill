"""The skill has to be a valid skill, and its documentation has to point at
files that exist.

If a path in SKILL.md breaks, the skill does not fail loudly — it degrades. The
agent reads the table, tries to open a reference that is not there, and carries
on with less context than it was promised. Nothing in the repo could see that
before this file.
"""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from tests.helpers import REPO_ROOT, SCRIPTS_DIR, run_script

# Any repo-relative path mentioned inside backticks, or as a markdown link
# target. Anchors and URLs are excluded.
BACKTICK_PATH_RE = re.compile(r'`([A-Za-z0-9_./-]+\.(?:md|py|pine|json|yml|txt))`')
MD_LINK_RE = re.compile(r'\[[^\]]*\]\(([^)#][^)]*)\)')
DIR_MENTION_RE = re.compile(r'`((?:references|scripts|assets|indicators|strategies|libraries|tests)'
                            r'/[A-Za-z0-9_./-]*/)`')

DOCS = ["SKILL.md", "README.md"] + [
    f"references/{p.name}" for p in sorted((REPO_ROOT / "references").glob("*.md"))]

# Paths that appear as examples rather than as references to real files.
EXAMPLE_PATHS = {
    "path/to/script.pine", "path/to/project", "src/<name>.pine", "signals.pine",
    "FILE.pine", "release/INPUTS.md", "your_project", "my_indicator.pine",
    ".pine-lint.json", "baseline.txt", "FILE", "notes.md",
}
# The docs' walkthroughs scaffold a project called `my_rsi_bands`. Anything
# named `my_*` is a placeholder the reader is meant to replace, by convention.
EXAMPLE_NAME_PREFIX = "my_"


class TestSkillFrontmatter(unittest.TestCase):
    def setUp(self):
        self.text = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")

    def test_starts_with_frontmatter(self):
        self.assertTrue(self.text.startswith("---\n"),
                        "SKILL.md must open with YAML frontmatter")

    def test_frontmatter_closes(self):
        self.assertIn("\n---\n", self.text[4:], "frontmatter block is not closed")

    def test_has_name_and_description(self):
        block = self.text[4:self.text.index("\n---\n", 4)]
        keys = {line.split(":", 1)[0].strip() for line in block.splitlines() if ":" in line}
        self.assertIn("name", keys)
        self.assertIn("description", keys)

    def test_name_matches_the_directory_convention(self):
        block = self.text[4:self.text.index("\n---\n", 4)]
        name = next(l.split(":", 1)[1].strip() for l in block.splitlines()
                    if l.startswith("name:"))
        self.assertRegex(name, r'^[a-z0-9][a-z0-9-]*$',
                         "skill name must be lower-kebab-case")

    def test_description_is_substantial(self):
        """The description is what decides whether the skill is invoked at all.
        A short one is a skill that never triggers."""
        block = self.text[4:self.text.index("\n---\n", 4)]
        desc = next(l.split(":", 1)[1].strip() for l in block.splitlines()
                    if l.startswith("description:"))
        self.assertGreater(len(desc), 200)


# Files that only ever exist inside a generated release/ directory, which is
# git-ignored. They are absent from a fresh clone by design, so requiring them
# to exist would make this check pass only on a machine that had run a release.
GENERATED_ARTIFACTS = {
    "PUBLISH_DESCRIPTION.md",
    "RELEASE_SUMMARY.txt",
    "INPUTS.md",
}


class TestDocumentedPathsExist(unittest.TestCase):
    """Resolution is deliberately generous, and the generosity is the design.

    A doc says `pine-v6-guide.md` meaning its sibling, `scripts/pine_lint.py`
    meaning the repo root, and `CHANGELOG.md` meaning "each project has one".
    All three are legitimate. What is never legitimate is a name that matches
    no file anywhere — which is what a typo or a renamed-but-not-updated
    reference looks like, and that is what this catches."""

    REPO_FILENAMES = {p.name for p in REPO_ROOT.rglob("*")
                      if p.is_file() and ".git" not in p.parts}

    def check(self, matches, doc):
        missing = []
        doc_dir = (REPO_ROOT / doc).parent
        for raw in matches:
            path = raw.strip()
            if not path or path in EXAMPLE_PATHS or "<" in path or "*" in path:
                continue
            if path.startswith(("http://", "https://", "mailto:")):
                continue
            if (REPO_ROOT / path).exists() or (doc_dir / path).exists():
                continue
            if Path(path).name.startswith(EXAMPLE_NAME_PREFIX):
                continue
            if Path(path).name in self.REPO_FILENAMES:
                continue
            if Path(path).name in GENERATED_ARTIFACTS:
                continue
            missing.append(f"{doc}: {path}")
        return missing

    def test_every_backticked_file_path_exists(self):
        missing = []
        for doc in DOCS:
            text = (REPO_ROOT / doc).read_text(encoding="utf-8")
            missing += self.check(BACKTICK_PATH_RE.findall(text), doc)
        self.assertEqual([], missing, msg="\n".join(missing))

    def test_every_backticked_directory_exists(self):
        missing = []
        for doc in DOCS:
            text = (REPO_ROOT / doc).read_text(encoding="utf-8")
            missing += self.check(DIR_MENTION_RE.findall(text), doc)
        self.assertEqual([], missing, msg="\n".join(missing))

    def test_every_relative_markdown_link_resolves(self):
        missing = []
        for doc in DOCS:
            text = (REPO_ROOT / doc).read_text(encoding="utf-8")
            base = (REPO_ROOT / doc).parent
            for target in MD_LINK_RE.findall(text):
                target = target.strip().split(" ")[0]
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                resolved = (base / target.split("#")[0]).resolve()
                if not resolved.exists():
                    missing.append(f"{doc}: {target}")
        self.assertEqual([], missing, msg="\n".join(missing))


class TestScriptsAreRunnable(unittest.TestCase):
    def test_every_script_compiles(self):
        proc = subprocess.run([sys.executable, "-m", "compileall", "-q", str(SCRIPTS_DIR)],
                              capture_output=True, text=True)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)

    def test_every_script_responds_to_help(self):
        """A script that cannot print --help is a script whose CLI is broken in
        a way nothing else here would notice."""
        broken = []
        for script in sorted(SCRIPTS_DIR.glob("*.py")):
            proc = subprocess.run([sys.executable, str(script), "--help"],
                                  capture_output=True, text=True)
            if proc.returncode != 0 or "usage" not in proc.stdout.lower():
                broken.append(f"{script.name}: rc={proc.returncode}")
        self.assertEqual([], broken, msg="\n".join(broken))

    def test_every_script_has_a_module_docstring(self):
        undocumented = []
        for script in sorted(SCRIPTS_DIR.glob("*.py")):
            text = script.read_text(encoding="utf-8")
            body = text.split("\n", 1)[1] if text.startswith("#!") else text
            if not body.lstrip().startswith('"""'):
                undocumented.append(script.name)
        self.assertEqual([], undocumented, msg="\n".join(undocumented))


class TestGeneratedRegions(unittest.TestCase):
    def test_generated_regions_are_current(self):
        proc = subprocess.run([sys.executable, str(SCRIPTS_DIR / "build_index.py"), "--check"],
                              capture_output=True, text=True, cwd=str(REPO_ROOT))
        self.assertEqual(0, proc.returncode,
                         "run: python3 scripts/build_index.py\n" + proc.stdout)

    def test_check_mode_detects_a_stale_region(self):
        """Proving the guard bites: without this, a --check that always passed
        would look identical to one that works."""
        readme = REPO_ROOT / "README.md"
        original = readme.read_text(encoding="utf-8")
        marker = "<!-- BEGIN GENERATED: projects -->\n"
        self.assertIn(marker, original)
        try:
            readme.write_text(original.replace(marker, marker + "| stale |\n", 1),
                              encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "build_index.py"), "--check"],
                capture_output=True, text=True, cwd=str(REPO_ROOT))
            self.assertEqual(1, proc.returncode)
            self.assertIn("OUT OF DATE", proc.stdout)
        finally:
            readme.write_text(original, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()


class TestLibrarySync(unittest.TestCase):
    """The inlined copies of pine_toolkit helpers must not drift.

    TradingView's `import` needs a PUBLISHED library, so until pine_toolkit is
    on their servers every script carries its own copy — the exact situation
    where copies diverge and nobody notices. The first run of this check found
    six drifted copies, one of which formatted the same volume with a different
    number of decimals in one indicator than in the other two.
    """

    def test_no_inlined_copy_has_drifted(self):
        proc = run_script("check_library_sync.py")
        self.assertEqual(0, proc.returncode,
                         "run: python3 scripts/check_library_sync.py\n" + proc.stdout)

    def test_check_actually_compares_something(self):
        """A check that finds no copies to compare would pass forever."""
        proc = run_script("check_library_sync.py", "--json")
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertGreater(payload["exports"], 5)
        self.assertGreater(payload["copies_checked"], 0)
