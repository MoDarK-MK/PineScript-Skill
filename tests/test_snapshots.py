"""Snapshot tests for the generated artifacts.

The other tests assert that a release bundle EXISTS and contains a few expected
strings. That catches a file going missing; it does not catch the publish
description quietly losing its disclosure section, or the inputs table changing
shape, or the summary dropping a check. Those are the changes that reach a
TradingView publish page without anyone reading them.

A stored golden file makes any such change show up in the diff of the commit
that caused it, which is the only place it can be judged.

To update a golden after an intentional change:
    python tests/test_snapshots.py --update
and then READ the diff before committing it. A golden updated without being read
is worse than no golden at all — it converts a silent change into a rubber stamp.
"""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.helpers import REPO_ROOT, run_script

SNAPSHOT_DIR = Path(__file__).parent / "fixtures" / "snapshots"
PROJECT_NAME = "snap_demo"

# Everything that legitimately changes run to run. Normalised rather than
# stripped, so a field disappearing entirely still shows up as a diff.
NORMALISERS = (
    (re.compile(r'^Generated \d{4}-\d{2}-\d{2}.*$', re.MULTILINE), 'Generated <DATE>'),
    (re.compile(r'\d{4}-\d{2}-\d{2}'), '<DATE>'),
    (re.compile(r'^(\s*)(v?)\d+\.\d+\.\d+', re.MULTILINE), r'\1\2<VERSION>'),
    (re.compile(r'© \w+', ), '© <AUTHOR>'),
    (re.compile(r'\r\n'), '\n'),
)


def normalise(text):
    for pattern, replacement in NORMALISERS:
        text = pattern.sub(replacement, text)
    return text.rstrip() + "\n"


def build_bundle(td):
    """Scaffolds a project from the shipped template and releases it, so the
    snapshot covers the template and the generator together — which is the pair
    a user actually receives."""
    proc = run_script("scaffold_project.py", "--kind", "indicator",
                      "--name", PROJECT_NAME, "--out", td)
    assert proc.returncode == 0, proc.stderr
    project = Path(td) / PROJECT_NAME
    proc = run_script("generate_release_bundle.py", project)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return project / "release"


ARTIFACTS = ("PUBLISH_DESCRIPTION.md", "RELEASE_SUMMARY.txt", "INPUTS.md")


class TestGeneratedArtifactSnapshots(unittest.TestCase):
    def test_artifacts_match_their_goldens(self):
        with tempfile.TemporaryDirectory() as td:
            release = build_bundle(td)
            for name in ARTIFACTS:
                golden = SNAPSHOT_DIR / (name + ".golden")
                with self.subTest(artifact=name):
                    self.assertTrue(
                        golden.exists(),
                        msg=f"no golden for {name}; run: python tests/test_snapshots.py --update")
                    actual = normalise((release / name).read_text(encoding="utf-8"))
                    expected = normalise(golden.read_text(encoding="utf-8"))
                    self.assertEqual(
                        expected, actual,
                        msg=(f"{name} changed.\n"
                             f"If that was intentional: python tests/test_snapshots.py --update\n"
                             f"Then read the diff before committing it."))

    def test_goldens_are_not_empty(self):
        """A golden truncated to nothing would make every comparison pass."""
        for name in ARTIFACTS:
            golden = SNAPSHOT_DIR / (name + ".golden")
            if golden.exists():
                with self.subTest(artifact=name):
                    self.assertGreater(len(golden.read_text(encoding="utf-8").strip()), 100)


def update_goldens():
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        release = build_bundle(td)
        for name in ARTIFACTS:
            shutil.copyfile(release / name, SNAPSHOT_DIR / (name + ".golden"))
            print("updated", (SNAPSHOT_DIR / (name + ".golden")).relative_to(REPO_ROOT))
    print()
    print("Now READ the diff. A golden updated without being read is a rubber stamp.")


if __name__ == "__main__":
    if "--update" in sys.argv:
        update_goldens()
    else:
        unittest.main()
