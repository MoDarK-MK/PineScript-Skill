import json
import tempfile
import unittest
from pathlib import Path

from tests.helpers import VALID_INDICATOR, run_script

import pine_lint


def lint_text(text):
    """Lint a Pine source string with the default config; returns LintResult."""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "script.pine"
        path.write_text(text, encoding="utf-8")
        return pine_lint.lint_file(str(path), dict(pine_lint.DEFAULT_CONFIG))


def codes(result):
    return {f.code for f in result.findings}


class TestRuleCatalog(unittest.TestCase):
    def test_has_27_rules_and_no_pine024(self):
        self.assertEqual(len(pine_lint.RULES), 27)
        self.assertNotIn("PINE024", pine_lint.RULES)
        self.assertIn("PINE001", pine_lint.RULES)
        self.assertIn("PINE028", pine_lint.RULES)

    def test_list_rules_cli(self):
        proc = run_script("pine_lint.py", "--list-rules")
        self.assertEqual(proc.returncode, 0)
        lines = [l for l in proc.stdout.splitlines() if l.strip()]
        self.assertEqual(len(lines), 27)


class TestCoreRules(unittest.TestCase):
    def test_valid_indicator_is_clean(self):
        result = lint_text(VALID_INDICATOR)
        self.assertEqual([], result.by_severity("error"),
                         msg=[f.msg for f in result.findings])
        self.assertTrue(result.ok())

    def test_missing_version_pragma(self):
        result = lint_text('indicator("X", overlay=true)\nplot(close)\n')
        self.assertIn("PINE001", codes(result))
        self.assertFalse(result.ok())

    def test_missing_declaration(self):
        result = lint_text("//@version=6\nplot(close)\n")
        self.assertIn("PINE002", codes(result))

    def test_deprecated_study(self):
        result = lint_text('//@version=6\nstudy("X")\nplot(close)\n')
        self.assertIn("PINE004", codes(result))

    def test_transp_removed(self):
        text = VALID_INDICATOR + "bgcolor(color.red, transp=80)\n"
        self.assertIn("PINE011", codes(lint_text(text)))

    def test_when_removed(self):
        text = (
            '//@version=6\nstrategy("S", overlay=true, default_qty_type=strategy.percent_of_equity, '
            "default_qty_value=10, commission_type=strategy.commission.percent, commission_value=0.1)\n"
            'strategy.entry("L", strategy.long, when=close > open)\n'
        )
        self.assertIn("PINE010", codes(lint_text(text)))

    def test_missing_overlay_warns(self):
        result = lint_text('//@version=6\nindicator("X")\nplot(close)\n')
        self.assertIn("PINE022", codes(result))
        # warning only — still ok() in non-strict mode, fails in strict
        self.assertTrue(result.ok())
        self.assertFalse(result.ok(strict=True))

    def test_unbalanced_parens(self):
        result = lint_text(VALID_INDICATOR + "x = math.max(1, 2\n")
        self.assertIn("PINE003", codes(result))

    def test_no_output_call(self):
        result = lint_text('//@version=6\nindicator("X", overlay=true)\nx = close\n')
        self.assertIn("PINE027", codes(result))


class TestSuppressions(unittest.TestCase):
    LONG_LINE = "x = 1  " + "// " + "z" * 130

    def test_finding_without_suppression(self):
        self.assertIn("PINE008", codes(lint_text(VALID_INDICATOR + self.LONG_LINE + "\n")))

    def test_disable_next_line(self):
        text = VALID_INDICATOR + "// pine-lint-disable-next-line PINE008\n" + self.LONG_LINE + "\n"
        self.assertNotIn("PINE008", codes(lint_text(text)))

    def test_disable_file_wide(self):
        text = "// pine-lint-disable PINE008\n" + VALID_INDICATOR + self.LONG_LINE + "\n"
        self.assertNotIn("PINE008", codes(lint_text(text)))


class TestCli(unittest.TestCase):
    def test_json_output(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "script.pine"
            path.write_text('//@version=6\nindicator("X")\nplot(close)\n', encoding="utf-8")
            proc = run_script("pine_lint.py", path, "--json")
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertIn("findings", payload)
        self.assertIn("summary", payload)
        self.assertIn("PINE022", {f["code"] for f in payload["findings"]})

    def test_missing_file_exits_1(self):
        proc = run_script("pine_lint.py", "does_not_exist.pine")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not found", proc.stderr)


if __name__ == "__main__":
    unittest.main()
