"""Tests for the tools added alongside the linter.

Each one here exists because the tool has a way of passing while doing nothing:
a builder that reports success on zero parts, a compatibility check that finds
no baseline and says everything is fine, a doctor that counts a skipped check as
a pass. Those are the cases under test, more than the happy paths.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import REPO_ROOT, run_script


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


MINIMAL = """// This source code is subject to the Mozilla Public License 2.0
//@version=6
indicator("Tiny", overlay=true)
int lengthInput = input.int(14, "Length", minval=1, maxval=200)
plot(ta.sma(close, lengthInput), title="SMA")
"""


class TestBuildPine(unittest.TestCase):
    def make_project(self, td):
        project = Path(td) / "demo"
        write(project / "src" / "demo.pine", MINIMAL)
        write(project / "version.json", json.dumps({"name": "demo", "version": "0.1.0"}))
        return project

    def test_split_then_build_reproduces_the_code(self):
        with tempfile.TemporaryDirectory() as td:
            project = self.make_project(td)
            before = (project / "src" / "demo.pine").read_text(encoding="utf-8")
            self.assertEqual(0, run_script("build_pine.py", project, "--split").returncode)
            self.assertEqual(0, run_script("build_pine.py", project).returncode)
            after = (project / "src" / "demo.pine").read_text(encoding="utf-8")
            # The banner is added; every non-blank code line must survive intact.
            self.assertEqual([l for l in before.splitlines() if l.strip()],
                             [l for l in after.splitlines()
                              if l.strip() and not l.startswith("// =")
                              and "GENERATED FILE" not in l
                              and "scripts/build_pine.py" not in l
                              and "Edit the parts" not in l])

    def test_check_detects_a_hand_edited_build_output(self):
        with tempfile.TemporaryDirectory() as td:
            project = self.make_project(td)
            run_script("build_pine.py", project, "--split")
            run_script("build_pine.py", project)
            self.assertEqual(0, run_script("build_pine.py", project, "--check").returncode)
            built = project / "src" / "demo.pine"
            built.write_text(built.read_text(encoding="utf-8") + "\n// sneaked in\n",
                             encoding="utf-8")
            self.assertEqual(1, run_script("build_pine.py", project, "--check").returncode)

    def test_split_refuses_to_run_twice(self):
        """Splitting again would shred parts that have already been edited."""
        with tempfile.TemporaryDirectory() as td:
            project = self.make_project(td)
            run_script("build_pine.py", project, "--split")
            proc = run_script("build_pine.py", project, "--split")
            self.assertNotEqual(0, proc.returncode)


class TestComplexity(unittest.TestCase):
    def test_reports_every_project(self):
        proc = run_script("complexity.py", "--json")
        self.assertEqual(0, proc.returncode, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertTrue(data["files"])

    def test_exported_functions_are_counted(self):
        """A library of exported helpers once reported zero functions."""
        proc = run_script("complexity.py", "--json")
        data = json.loads(proc.stdout)
        libs = [f for f in data["files"] if "pine_toolkit" in f["file"]]
        if not libs:
            self.skipTest("pine_toolkit not in this checkout")
        self.assertGreater(libs[0]["functions"], 0)


class TestBudget(unittest.TestCase):
    def test_reports_and_does_not_crash(self):
        proc = run_script("check_budget.py", "--json")
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        json.loads(proc.stdout)

    def test_undeclared_projects_are_named_not_passed(self):
        """A project with no budget.json must be reported, never counted as ok."""
        proc = run_script("check_budget.py", "--json")
        data = json.loads(proc.stdout)
        for entry in data["projects"]:
            if entry["status"] == "no-budget":
                self.assertIn(entry["project"], data["undeclared"])


class TestPersianReference(unittest.TestCase):
    def test_is_current(self):
        proc = run_script("build_fa_reference.py", "--check")
        self.assertEqual(0, proc.returncode,
                         "run: python3 scripts/build_fa_reference.py\n" + proc.stdout)

    def test_every_rule_has_a_translation(self):
        """An untranslated rule falls back to English and is listed. That is the
        honest behaviour, but the list should be empty."""
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import build_fa_reference
        _body, untranslated = build_fa_reference.render()
        self.assertEqual([], untranslated)


class TestDoctor(unittest.TestCase):
    # Always --skip "unit tests": doctor runs the whole suite, and this file is
    # in it. Without the skip the two call each other until something gives up.
    ARGS = ("doctor.py", "--fast", "--skip", "unit tests", "--json")

    def test_runs_and_reports_each_check(self):
        proc = run_script(*self.ARGS)
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        data = json.loads(proc.stdout)
        self.assertGreaterEqual(len(data["checks"]), 8)

    def test_a_skipped_check_is_not_counted_as_passing(self):
        proc = run_script(*self.ARGS)
        data = json.loads(proc.stdout)
        statuses = {c["name"]: c["status"] for c in data["checks"]}
        self.assertEqual("skip", statuses.get("rule mutation"))
        self.assertIn("rule mutation", data["skipped"])
        # And crucially: skipped never contributes to the verdict.
        self.assertEqual("fail" if data["failed"] else "pass", data["verdict"])


class TestInputsCompat(unittest.TestCase):
    def test_no_baseline_is_reported_not_passed_silently(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "demo"
            write(project / "src" / "demo.pine", MINIMAL)
            write(project / "version.json", json.dumps({"name": "demo", "version": "0.1.0"}))
            proc = run_script("check_inputs_compat.py", project, "--json")
            self.assertEqual(0, proc.returncode)
            self.assertEqual("no-baseline", json.loads(proc.stdout)["status"])

    def test_a_rename_is_breaking(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "demo"
            write(project / "src" / "demo.pine", MINIMAL)
            write(project / "version.json", json.dumps({"name": "demo", "version": "0.1.0"}))
            run_script("generate_release_bundle.py", project)
            table = project / "release" / "INPUTS.md"
            table.write_text(table.read_text(encoding="utf-8")
                             .replace("| Length |", "| Period |", 1), encoding="utf-8")
            proc = run_script("check_inputs_compat.py", project, "--json")
            data = json.loads(proc.stdout)
            self.assertTrue(data["breaking"])
            self.assertIn("Period", data["removed_or_renamed"])

    def test_a_title_containing_a_pipe_is_not_reported_as_renamed(self):
        """The generated table escapes a pipe as \\|. Splitting on bare pipes
        tore such a row apart and invented a rename."""
        piped = MINIMAL.replace('input.int(14, "Length", minval=1, maxval=200)',
                                'input.int(14, "Fast | Slow", minval=1, maxval=200)')
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "demo"
            write(project / "src" / "demo.pine", piped)
            write(project / "version.json", json.dumps({"name": "demo", "version": "0.1.0"}))
            run_script("generate_release_bundle.py", project)
            proc = run_script("check_inputs_compat.py", project, "--json")
            data = json.loads(proc.stdout)
            self.assertFalse(data["breaking"], data)
            self.assertEqual([], data["removed_or_renamed"])


class TestLintOutputFormats(unittest.TestCase):
    FIXTURE = "tests/fixtures/compile_errors/var_array_realtime_growth.pine"

    def test_editor_format_is_path_line_col(self):
        proc = run_script("pine_lint.py", self.FIXTURE, "--format", "editor")
        first = proc.stdout.strip().splitlines()[0]
        self.assertRegex(first, r"^.+\.pine:\d+:\d+: (error|warning|info): ")

    def test_github_format_is_an_annotation(self):
        proc = run_script("pine_lint.py", self.FIXTURE, "--format", "github")
        first = proc.stdout.strip().splitlines()[0]
        self.assertRegex(first, r"^::(error|warning|notice) file=.+,line=\d+,title=PINE\d{3}::")

    def test_annotations_are_single_line(self):
        proc = run_script("pine_lint.py", self.FIXTURE, "--format", "github")
        for line in proc.stdout.strip().splitlines():
            self.assertTrue(line.startswith("::"),
                            f"a wrapped annotation loses everything after the break: {line}")


class TestProfiles(unittest.TestCase):
    FIXTURE = "tests/fixtures/compile_errors/var_array_realtime_growth.pine"

    def test_dev_does_not_fail_on_a_warning(self):
        self.assertEqual(0, run_script("pine_lint.py", self.FIXTURE, "--profile", "dev").returncode)

    def test_publish_does(self):
        self.assertEqual(1, run_script("pine_lint.py", self.FIXTURE,
                                       "--profile", "publish").returncode)

    def test_a_profile_never_invents_a_finding(self):
        """Filtering only. Anything `dev` reports must also be in `all`."""
        dev = run_script("pine_lint.py", self.FIXTURE, "--profile", "dev", "--json")
        every = run_script("pine_lint.py", self.FIXTURE, "--profile", "all", "--json")
        dev_codes = {f["code"] for f in json.loads(dev.stdout)["findings"]}
        all_codes = {f["code"] for f in json.loads(every.stdout)["findings"]}
        self.assertTrue(dev_codes <= all_codes)


if __name__ == "__main__":
    unittest.main()
