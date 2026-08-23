"""Parity check for code duplicated across Pine projects.

Pine has no local imports, so the reversal scoring engine exists twice: once in
the indicator and once in the strategy. A comment saying "keep in sync" is not
a mechanism — this is. Change one copy and the suite fails until you change the
other, which forces both to move in the same commit.

Both copies live in directories that are private and untracked, so on a clean
checkout they are simply not there. This SKIPS in that case rather than passing:
a check that silently succeeds because its inputs vanished is worse than one
that fails, because it still reports green.
"""
import re
import unittest

from tests.helpers import REPO_ROOT

BEGIN = "// ————— SHARED SCORING ENGINE — BEGIN"
END = "// ————— SHARED SCORING ENGINE — END"

SEARCH_DIRS = ("indicators", "strategies", "libraries", "assets")


def copies():
    """Every .pine carrying the marker pair, found rather than listed.

    Discovery beats a hard-coded list twice over: a new pair of files is covered
    without editing this test, and no private project path appears in a tracked
    file."""
    found = []
    for parent in SEARCH_DIRS:
        base = REPO_ROOT / parent
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.pine")):
            if "release" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            if BEGIN in text and END in text:
                found.append(str(path.relative_to(REPO_ROOT)).replace("\\", "/"))
    return found


def extract(rel):
    text = (REPO_ROOT / rel).read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        return None
    body = text.split(BEGIN, 1)[1].split(END, 1)[0]
    # Normalise line endings only; everything else must match exactly.
    return body.replace("\r\n", "\n")


class TestSharedEngine(unittest.TestCase):
    def setUp(self):
        # Skip, never pass, when there is nothing to compare. A parity check that
        # succeeds because both of the things it compares are missing still
        # reports green, which is the worst outcome for a test whose entire job
        # is to notice a difference.
        self.found = copies()
        if len(self.found) < 2:
            self.skipTest(
                "fewer than two files carry the SHARED SCORING ENGINE markers in "
                "this checkout (found: %s)" % (self.found or "none"))

    def test_every_copy_declares_the_markers(self):
        missing = [rel for rel in self.found if extract(rel) is None]
        self.assertEqual([], missing,
                         msg=f"files missing the SHARED SCORING ENGINE markers: {missing}")

    def test_copies_are_identical(self):
        bodies = {rel: extract(rel) for rel in self.found}
        reference_rel = self.found[0]
        reference = bodies[reference_rel]
        for rel, body in bodies.items():
            if rel == reference_rel:
                continue
            self.assertEqual(
                reference, body,
                msg=(f"the shared engine in {rel} has drifted from {reference_rel}.\n"
                     f"Both copies must change in the same commit — Pine cannot import "
                     f"one from the other."))

    def test_the_block_is_not_empty(self):
        """A marker pair around nothing would make the parity test vacuous."""
        for rel in self.found:
            body = extract(rel)
            self.assertIn("countConfirmations", body,
                          msg=f"{rel}: the marked block no longer contains the scoring call")
            self.assertGreater(len([l for l in body.splitlines() if l.strip()]), 10,
                               msg=f"{rel}: the marked block looks suspiciously short")

    def test_both_projects_are_versioned(self):
        """If the engine changes, both projects need a release — this at least
        guarantees both have a version to bump."""
        import json
        for rel in self.found:
            project = (REPO_ROOT / rel).parent.parent
            version = json.loads((project / "version.json").read_text(encoding="utf-8"))
            self.assertIn("version", version, msg=f"{project.name} has no version")


if __name__ == "__main__":
    unittest.main()
