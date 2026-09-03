"""The drift checker's blind spot, and why it existed.

`check_library_sync` compared functions BY NAME. Three helpers are exported by
the library as `textColor`, `mutedColor` and `panelColor`, and every script that
uses them declares its copy as `getTextColor`, `getMutedColor` and
`getPanelColor` - so the names never matched and the copies were never compared
at all. Six copies were being checked; there are twenty-one.

The scripts cannot drop the `get` prefix. `textColor` and `mutedColor` are
already variables in the same files:

    color textColor = getTextColor(themeInput)

so renaming the function to match the library would shadow the value it
produces - the same class of collision that has already cost this repo a
release. The alias map is the fix; renaming would have been the bug.
"""
import sys
import unittest

from tests.helpers import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_library_sync as sync


class TestAliasMap(unittest.TestCase):
    def test_the_prefixed_names_are_mapped_to_the_library(self):
        for local, canonical in (("getTextColor", "textColor"),
                                 ("getMutedColor", "mutedColor"),
                                 ("getPanelColor", "panelColor")):
            self.assertEqual(canonical, sync.LOCAL_ALIASES.get(local))

    def test_every_alias_names_a_real_export(self):
        """An alias pointing at a function the library does not export would
        silently skip the copy rather than compare it — which is the exact
        failure this map exists to end."""
        lines = sync.read_lines(sync.LIBRARY)
        exported = sync.collect_functions(lines, sync.EXPORT_RE)
        for local, canonical in sync.LOCAL_ALIASES.items():
            self.assertIn(canonical, exported,
                          f"{local} is mapped to {canonical}, which the library "
                          f"does not export")

    def test_the_prefix_is_load_bearing(self):
        """`textColor` is a VARIABLE in the scripts that use it, so a copy named
        after the library would shadow the value it produces. This asserts the
        collision is real, so nobody 'tidies' the alias map away."""
        found = 0
        for base in ("indicators", "strategies"):
            for path in (REPO_ROOT / base).glob("*/src/*.pine"):
                text = path.read_text(encoding="utf-8")
                if "color textColor" in text and "getTextColor(" in text:
                    found += 1
        self.assertGreater(found, 0,
                           "no script declares `color textColor` any more — if "
                           "that is really true, the alias map can go and the "
                           "copies can take the library's names")


class TestConstantNormalisation(unittest.TestCase):
    """A script names its themes; a library cannot, because the constant belongs
    to the consumer. Without normalising that, twenty-seven style differences
    buried one real one — a missing transparency clamp."""

    def test_the_theme_constants_normalise_to_their_values(self):
        body = ["    theme == THEME_LIGHT ? #131722 : #d1d4dc"]
        self.assertEqual(['theme == "Light" ? #131722 : #d1d4dc'],
                         sync.normalise(body))

    def test_a_name_merely_containing_the_constant_is_untouched(self):
        body = ["    x = THEME_LIGHTNESS + 1"]
        self.assertEqual(["x = THEME_LIGHTNESS + 1"], sync.normalise(body))

    def test_normalisation_does_not_hide_a_real_difference(self):
        """The clamp is what the constant was hiding, so a body without it must
        still compare unequal."""
        with_clamp = ["    color.new(theme == THEME_LIGHT ? #ffffff : #131722, "
                      "math.max(0, math.min(100, transp)))"]
        without = ["    color.new(theme == THEME_LIGHT ? #ffffff : #131722, transp)"]
        self.assertNotEqual(sync.normalise(with_clamp), sync.normalise(without))


class TestNoDriftRemains(unittest.TestCase):
    def test_the_repo_has_no_undeclared_drift(self):
        """Anything genuinely different carries a `library-sync-exempt` comment
        saying why. This asserts nothing is different by accident."""
        import subprocess
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "check_library_sync.py")],
            capture_output=True, text=True, cwd=str(REPO_ROOT))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("0 drifted", result.stdout)


if __name__ == "__main__":
    unittest.main()
