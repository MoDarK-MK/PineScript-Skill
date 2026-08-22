"""Consistency checks between the code and the documentation.

Every one of these exists because the corresponding drift actually happened:
rule counts were hand-maintained in five places and went stale, a rule shipped
undocumented, and a version.json fell out of step with its CHANGELOG.
"""
import json
import re
import unittest

from tests.helpers import REPO_ROOT

import pine_lint

RULE_HEADING_RE = re.compile(r'^### (PINE\d{3}) — (error|warning|info) — ', re.MULTILINE)
# Any "<n> rules" / "<n>-rule" / "<n>-Rule" claim in prose.
COUNT_CLAIM_RE = re.compile(r'\b(\d+)[\s-](?:rule|Rule)s?\b')
# A claimed code span, e.g. "PINE001–PINE045" or "PINE001-045".
SPAN_CLAIM_RE = re.compile(r'PINE0*(\d{1,3})\s*[–-]\s*(?:PINE)?0*(\d{1,3})')

DOCS_WITH_COUNTS = ["README.md", "SKILL.md", "references/lint-rules.md"]


def read(rel):
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


class TestRuleDocumentation(unittest.TestCase):
    def test_every_rule_is_documented(self):
        documented = set(RULE_HEADING_RE.findall(read("references/lint-rules.md")))
        documented_codes = {code for code, _sev in documented}
        missing = sorted(set(pine_lint.RULES) - documented_codes)
        self.assertEqual([], missing,
                         msg=f"rules with no section in lint-rules.md: {missing}")

    def test_no_documented_rule_is_unknown(self):
        documented_codes = {c for c, _s in RULE_HEADING_RE.findall(read("references/lint-rules.md"))}
        extra = sorted(documented_codes - set(pine_lint.RULES))
        self.assertEqual([], extra,
                         msg=f"lint-rules.md documents codes that do not exist: {extra}")

    def test_documented_severities_match_the_catalog(self):
        mismatches = []
        for code, sev in RULE_HEADING_RE.findall(read("references/lint-rules.md")):
            if code in pine_lint.RULES and pine_lint.RULES[code][0] != sev:
                mismatches.append(f"{code}: doc says {sev}, code says {pine_lint.RULES[code][0]}")
        self.assertEqual([], mismatches, msg=mismatches)


class TestRuleCountClaims(unittest.TestCase):
    def test_prose_rule_counts_match_the_catalog(self):
        actual = len(pine_lint.RULES)
        wrong = []
        for rel in DOCS_WITH_COUNTS:
            for line in read(rel).splitlines():
                for claimed in COUNT_CLAIM_RE.findall(line):
                    # Only treat it as a claim about THIS catalog when the line
                    # is talking about linting, not e.g. "4-rule risk module".
                    if "lint" not in line.lower() and "Linter" not in line:
                        continue
                    if int(claimed) != actual:
                        wrong.append(f"{rel}: claims {claimed} rules, catalog has {actual}\n  {line.strip()}")
        self.assertEqual([], wrong, msg="\n".join(wrong))

    def test_code_span_claims_match_the_catalog(self):
        codes = sorted(int(c[4:]) for c in pine_lint.RULES)
        lo, hi = codes[0], codes[-1]
        wrong = []
        for rel in DOCS_WITH_COUNTS:
            for line in read(rel).splitlines():
                if "PINE" not in line:
                    continue
                for a, b in SPAN_CLAIM_RE.findall(line):
                    # Ignore narrow spans that describe a subset (e.g. "PINE029–PINE035").
                    if int(a) != lo:
                        continue
                    if int(b) != hi:
                        wrong.append(f"{rel}: claims PINE{a}-PINE{b}, catalog ends at PINE{hi:03d}\n  {line.strip()}")
        self.assertEqual([], wrong, msg="\n".join(wrong))

    def test_pine024_is_still_vacant(self):
        self.assertNotIn("PINE024", pine_lint.RULES)

    def test_rule_codes_have_no_other_gaps(self):
        codes = sorted(int(c[4:]) for c in pine_lint.RULES)
        expected = [n for n in range(codes[0], codes[-1] + 1) if n != 24]
        self.assertEqual(expected, codes,
                         msg="rule numbering has an unintended gap; only PINE024 may be vacant")


class TestProjectVersions(unittest.TestCase):
    """version.json and the CHANGELOG's newest release must agree."""

    def project_dirs(self):
        for parent in ("indicators", "strategies", "libraries"):
            base = REPO_ROOT / parent
            if base.is_dir():
                for child in sorted(base.iterdir()):
                    if (child / "version.json").exists():
                        yield child

    def test_version_json_matches_changelog_head(self):
        problems = []
        for project in self.project_dirs():
            version = json.loads((project / "version.json").read_text(encoding="utf-8"))["version"]
            changelog = (project / "CHANGELOG.md").read_text(encoding="utf-8")
            released = re.findall(r'^## \[(\d+\.\d+\.\d+)\]', changelog, re.MULTILINE)
            if not released:
                problems.append(f"{project.name}: CHANGELOG has no released version heading")
            elif released[0] != version:
                problems.append(
                    f"{project.name}: version.json says {version}, "
                    f"newest CHANGELOG entry is {released[0]}")
        self.assertEqual([], problems, msg="\n".join(problems))

    def test_changelog_versions_descend(self):
        problems = []
        for project in self.project_dirs():
            changelog = (project / "CHANGELOG.md").read_text(encoding="utf-8")
            released = re.findall(r'^## \[(\d+\.\d+\.\d+)\]', changelog, re.MULTILINE)
            parsed = [tuple(int(p) for p in v.split(".")) for v in released]
            if parsed != sorted(parsed, reverse=True):
                problems.append(f"{project.name}: CHANGELOG versions are not newest-first: {released}")
        self.assertEqual([], problems, msg="\n".join(problems))

    def test_every_project_has_a_source_file(self):
        problems = []
        for project in self.project_dirs():
            name = json.loads((project / "version.json").read_text(encoding="utf-8"))["name"]
            if not (project / "src" / f"{name}.pine").exists():
                problems.append(f"{project.name}: no src/{name}.pine")
        self.assertEqual([], problems, msg="\n".join(problems))


if __name__ == "__main__":
    unittest.main()
