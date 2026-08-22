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

def lint_text(text):
    """Lint a Pine source string with the default config; returns LintResult.

    Lives here rather than in one test module so every test file can use it
    without importing another test file — an import path that breaks depending
    on how unittest was invoked."""
    import tempfile
    import pine_lint
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "script.pine"
        path.write_text(text, encoding="utf-8")
        return pine_lint.lint_file(str(path), dict(pine_lint.DEFAULT_CONFIG))


def codes(result):
    """The set of rule codes in a LintResult."""
    return {f.code for f in result.findings}


VALID_INDICATOR = '''\
// This source code is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/
//@version=6
indicator("Test Indicator", "TI", overlay=true)
plot(close, title="Close")
'''

# Minimal strategy that is clean under EVERY rule, including PINE021 and the
# strategy rules PINE029-PINE035. Strategy-rule tests mutate this string so the
# "clean" baseline comes for free.
VALID_STRATEGY = '''\
// This source code is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/
//@version=6
strategy("Test Strategy", "TS", overlay=true,
     default_qty_type=strategy.percent_of_equity, default_qty_value=10,
     initial_capital=10000, commission_type=strategy.commission.percent,
     commission_value=0.05, slippage=1)
float fastMa = ta.ema(close, 10)
float slowMa = ta.ema(close, 30)
bool goLong = ta.crossover(fastMa, slowMa)
if goLong
    strategy.entry("Long", strategy.long)
if strategy.position_size > 0
    float avgPrice = strategy.position_avg_price
    strategy.exit("Long Exit", "Long", stop=avgPrice * 0.98, limit=avgPrice * 1.04)
plot(fastMa, title="Fast MA")
'''
