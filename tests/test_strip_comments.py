"""The released copy carries no comments, and behaves exactly as the source did.

The second half of that sentence is the one worth testing. Removing comments
looks trivial until a tooltip contains a URL, at which point cutting on the
first `//` produces an unterminated string and a script that will not compile.
"""
import unittest
from pathlib import Path

from tests.helpers import REPO_ROOT

from strip_comments import code_before_comment, strip_pine_comments
from pine_interp import run_source, synthetic_bars


class TestCodeBeforeComment(unittest.TestCase):
    def test_a_trailing_comment_is_removed_and_the_code_kept(self):
        self.assertEqual("int x = 5  ", code_before_comment("int x = 5  // why"))

    def test_a_double_slash_inside_a_string_is_not_a_comment(self):
        """The failure this function exists to avoid. Splitting on the first
        `//` here leaves `plot(close, title = "https:` — an unterminated string
        literal, and a hard compile error."""
        line = 'plot(close, title = "https://example.com")'
        self.assertEqual(line, code_before_comment(line))

    def test_an_escaped_quote_does_not_end_the_string(self):
        line = 'plot(close, title = "he said \\"go//stop\\" once")'
        self.assertEqual(line, code_before_comment(line))

    def test_an_apostrophe_inside_a_double_quoted_string_is_text(self):
        line = "plot(close, title = \"the swing's high\")  // note"
        self.assertEqual("plot(close, title = \"the swing's high\")  ",
                         code_before_comment(line))

    def test_a_line_that_is_only_a_comment_leaves_nothing(self):
        self.assertEqual("", code_before_comment("    // just a note").strip())


class TestStripPineComments(unittest.TestCase):
    def test_the_version_directive_survives(self):
        """`//@version=6` looks like a comment and is a compiler directive.
        Removing it changes which language the script is compiled as."""
        out = strip_pine_comments('//@version=6\nindicator("T")\n// gone\n')
        self.assertIn("//@version=6", out)
        self.assertNotIn("gone", out)

    def test_the_licence_header_survives(self):
        src = ("// This Pine Script code is subject to the terms of the MPL 2.0\n"
               "// © someone\n"
               "\n"
               "//@version=6\n"
               'indicator("T")\n'
               "// an ordinary note\n")
        out = strip_pine_comments(src)
        self.assertIn("Mozilla", out.replace("MPL 2.0", "Mozilla"))
        self.assertIn("©", out)
        self.assertNotIn("ordinary note", out)

    def test_the_older_licence_wording_also_survives(self):
        """TradingView has used two wordings. Matching only the newer one
        dropped the licence from every project scaffolded before the change,
        and the release still claimed a licence header was present."""
        src = "\n".join([
            "//@version=6",
            "// This source code is subject to the terms of the Mozilla Public "
            "License 2.0",
            'indicator("T")',
            ""])
        self.assertIn("This source code", strip_pine_comments(src))

    def test_the_licence_survives_below_the_version_directive(self):
        """Where it actually sits in a generated project: the part builder
        writes the version line first. A rule that only protected a LEADING
        header removed the licence from every one of them."""
        src = "\n".join([
            "//@version=6",
            "// © someone",
            'indicator("T")',
            "// an ordinary note",
            ""])
        out = strip_pine_comments(src)
        self.assertIn("©", out)
        self.assertNotIn("ordinary note", out)

    def test_an_ordinary_comment_near_the_top_is_still_removed(self):
        """Being early does not make a comment a header."""
        src = ("// © someone\n"
               "//@version=6\n"
               "// a long explanation of the design\n"
               'indicator("T")\n')
        out = strip_pine_comments(src)
        self.assertNotIn("long explanation", out)

    def test_comment_only_lines_are_removed_not_blanked(self):
        """The point is a shorter file, not the same file with holes in it."""
        src = '//@version=6\nindicator("T")\n// one\n// two\n// three\nplot(close)\n'
        out = strip_pine_comments(src)
        self.assertEqual(['//@version=6', 'indicator("T")', "plot(close)"],
                         out.strip().split("\n"))

    def test_runs_of_blank_lines_collapse_to_one(self):
        src = '//@version=6\nindicator("T")\n\n\n\nplot(close)\n'
        self.assertNotIn("\n\n\n", strip_pine_comments(src))

    def test_indentation_of_surviving_code_is_untouched(self):
        """Pine blocks are indentation-sensitive, so a stripper that trimmed
        leading whitespace would silently restructure every if and for."""
        src = ('//@version=6\nindicator("T")\n'
               "if close > open\n"
               "    // a note\n"
               "    int x = 1  // trailing\n"
               "    plot(x)\n")
        out = strip_pine_comments(src)
        self.assertIn("    int x = 1", out)
        self.assertIn("    plot(x)", out)
        self.assertNotIn("a note", out)
        self.assertNotIn("trailing", out)


PROJECTS = [p for p in (REPO_ROOT / "indicators").glob("*/src/*.pine")] if \
    (REPO_ROOT / "indicators").exists() else []


@unittest.skipUnless(PROJECTS, "no indicator sources in this checkout")
class TestStrippingChangesNothing(unittest.TestCase):
    """The property that makes this safe to do by default.

    A comment carries no behaviour, so a script with them removed must produce
    exactly the drawings, plots and alerts the original did. This runs the real
    indicators both ways and compares — it is slower than the unit tests above
    and it is the one that would actually catch a stripper that ate code."""

    @staticmethod
    def fingerprint(res):
        drawings = [(d.kind, tuple(sorted((k, str(v)) for k, v in d.props.items())))
                    for d in res.drawings]
        plots = {k: [str(v) for v in vals] for k, vals in res.plots.items()}
        return drawings, plots, len(res.alerts), res.bars

    def test_the_stripped_script_behaves_identically(self):
        bars = synthetic_bars(150)
        for path in PROJECTS:
            with self.subTest(project=path.parent.parent.name):
                src = path.read_text(encoding="utf-8")
                stripped = strip_pine_comments(src)
                self.assertLess(len(stripped), len(src), "nothing was removed")
                self.assertEqual(self.fingerprint(run_source(src, bars)),
                                 self.fingerprint(run_source(stripped, bars)))


if __name__ == "__main__":
    unittest.main()
