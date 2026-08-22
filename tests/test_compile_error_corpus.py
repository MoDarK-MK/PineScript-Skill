"""The compile-error corpus: every TradingView failure this project has actually
hit, kept as a minimal reproduction that the linter must keep catching.

The pattern that produced this file was: ship a script, the user pastes it,
TradingView rejects it, fix it, add a rule. That loop only pays off if the rule
can never regress — hence a fixture per incident rather than a note in a
changelog.

Each fixture declares the rule that must fire in its header comment, so adding
a new incident is one file, not one file plus a test.
"""
import re
import unittest
from pathlib import Path

from tests.helpers import REPO_ROOT

import pine_lint

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "compile_errors"
EXPECTED_RULE_RE = re.compile(r'^// FIXTURE — must be caught by (PINE\d{3})', re.MULTILINE)


def fixtures():
    return sorted(FIXTURE_DIR.glob("*.pine"))


class TestCompileErrorCorpus(unittest.TestCase):
    def test_corpus_is_not_empty(self):
        self.assertTrue(fixtures(), msg=f"no fixtures found in {FIXTURE_DIR}")

    def test_every_fixture_declares_its_rule(self):
        undeclared = [f.name for f in fixtures()
                      if not EXPECTED_RULE_RE.search(f.read_text(encoding="utf-8"))]
        self.assertEqual([], undeclared,
                         msg=f"fixtures with no '// FIXTURE — must be caught by PINExxx' header: {undeclared}")

    def test_every_fixture_is_caught_by_its_rule(self):
        failures = []
        for path in fixtures():
            text = path.read_text(encoding="utf-8")
            expected = EXPECTED_RULE_RE.search(text).group(1)
            result = pine_lint.lint_file(str(path), dict(pine_lint.DEFAULT_CONFIG))
            found = {f.code for f in result.findings}
            if expected not in found:
                failures.append(f"{path.name}: expected {expected}, got {sorted(found) or 'nothing'}")
        self.assertEqual([], failures, msg="\n".join(failures))

    def test_every_expected_rule_still_exists(self):
        missing = []
        for path in fixtures():
            expected = EXPECTED_RULE_RE.search(path.read_text(encoding="utf-8")).group(1)
            if expected not in pine_lint.RULES:
                missing.append(f"{path.name} expects {expected}, which is not in the catalog")
        self.assertEqual([], missing, msg="\n".join(missing))

    def test_the_error_map_documents_every_corpus_rule(self):
        """Each fixture's rule should appear in the CE-code table in lint-rules.md,
        so someone holding a TradingView error message can find it."""
        catalog = (REPO_ROOT / "references" / "lint-rules.md").read_text(encoding="utf-8")
        table = catalog.split("## When TradingView gives you an error code", 1)
        self.assertEqual(2, len(table), msg="the error-code table is missing from lint-rules.md")
        table_text = table[1].split("\n## ", 1)[0]
        undocumented = []
        for path in fixtures():
            expected = EXPECTED_RULE_RE.search(path.read_text(encoding="utf-8")).group(1)
            if expected not in table_text:
                undocumented.append(f"{expected} ({path.name})")
        self.assertEqual([], undocumented,
                         msg=f"rules missing from the error-code table: {undocumented}")

    def test_fixtures_are_excluded_from_the_linted_source_tree(self):
        """CI lints assets/references/indicators/strategies. The corpus lives
        under tests/ precisely so deliberately-broken files never fail CI."""
        for path in fixtures():
            rel = path.relative_to(REPO_ROOT).as_posix()
            self.assertTrue(rel.startswith("tests/"),
                            msg=f"{rel} is outside tests/ and would break the CI lint")


if __name__ == "__main__":
    unittest.main()
