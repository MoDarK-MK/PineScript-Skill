"""Shared helpers for the test suite: import the scripts/ modules and run
them as CLIs the same way a user would."""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def run_script(script_name, *args, cwd=None):
    """Run scripts/<script_name> with the current interpreter; returns CompletedProcess."""
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script_name), *[str(a) for a in args]],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


VALID_INDICATOR = '''\
// This source code is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/
//@version=6
indicator("Test Indicator", "TI", overlay=true)
plot(close, title="Close")
'''
