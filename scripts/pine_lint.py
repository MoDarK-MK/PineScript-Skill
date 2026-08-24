#!/usr/bin/env python3
"""
pine_lint.py - Rule-based, OFFLINE linter for TradingView Pine Script (v5/v6).

This is NOT a compiler. TradingView has no public compiler CLI or API, so this
tool cannot guarantee a script will compile or run correctly on TradingView. It
catches structural/style/correctness issues via pattern matching, fact-checked
against TradingView's official docs (migration guide, limitations page, style
guide) as of mid-2026.

Usage:
    python3 pine_lint.py path/to/script.pine [--config .pine-lint.json]
                                              [--json] [--strict] [--list-rules]
                                              [--fix [--dry-run]]

Exit codes:
    0 = no errors (warnings/info may still print; --strict also fails on warnings)
    1 = at least one error (or, with --strict, at least one warning)

Suppressing a rule inline:
    // pine-lint-disable-next-line PINE008
    some_very_long_line_that_you_have_reviewed_and_accept = 1

    // pine-lint-disable-line PINE008
    another_long_line = 1  // suppresses for THIS line

    // pine-lint-disable PINE018,PINE008
    (anywhere in the file — suppresses those codes for the whole file)
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_CONFIG = {
    "max_line_length": 120,
    "max_plot_calls": 64,
    "plot_calls_warn_ratio": 0.75,
    "max_drawing_default": 50,
    "max_drawing_hard": 500,
    "max_polyline": 100,
    "max_tables": 9,
    "warn_on_security_lookahead": True,
    "max_requests": 40,
    "request_warn_ratio": 0.75,
    "max_loop_iterations": 100000,
}

# Profiles exist because the same findings are not equally useful at every
# moment. Mid-edit you want the things that stop a paste from compiling and
# nothing else; before publishing you want everything, including the cosmetic
# rules that would be noise while you are still moving code around.
#
# A profile only ever CHANGES SEVERITY OR HIDES — it never invents a finding, so
# nothing can be caught by `dev` and missed by `publish`.
PROFILES = {
    # Everything, warnings fatal. What CI and the release bundler use.
    "publish": {"min_severity": "info", "strict": True},
    # Errors only, non-fatal warnings hidden. For the edit loop.
    "dev": {"min_severity": "error", "strict": False},
    # Everything, nothing fatal. The default when no profile is named.
    "all": {"min_severity": "info", "strict": False},
}
SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}

# ---------------------------------------------------------------------------
# Rule catalog — single source of truth for severities + summaries.
# Keep in sync with references/lint-rules.md (run --list-rules to check).
# ---------------------------------------------------------------------------
RULES = {
    "PINE001": ("error", "Missing or malformed //@version= pragma"),
    "PINE002": ("error", "No indicator()/strategy()/library() declaration found"),
    "PINE003": ("error", "Unbalanced parentheses or brackets"),
    "PINE004": ("error", "Deprecated study()/security() syntax"),
    "PINE005": ("warning", "Accumulator reassigned without 'var' (resets every bar)"),
    "PINE006": ("warning", "request.security() without an explicit lookahead="),
    "PINE007": ("warning", "input.*() call missing a title"),
    "PINE008": ("warning", "Line exceeds configured max length"),
    "PINE009": ("warning", "Approaching/over the 64 plot-count limit"),
    "PINE010": ("error", "when= parameter used (removed in Pine v6)"),
    "PINE011": ("error", "transp= parameter used (removed in Pine v6)"),
    "PINE012": ("error", "linewidth below the v6 minimum of 1"),
    "PINE013": ("error", "switch statement missing a default '=>' arm (required in v6)"),
    "PINE014": ("error", "History-referencing operator [] used on a literal/constant (invalid in v6)"),
    "PINE015": ("error", "Same named parameter repeated in one call (compile error in v6)"),
    "PINE016": ("warning", "timeframe.period compared to a unit string with no multiplier"),
    "PINE017": ("warning", "Possible v6 lazy and/or evaluation trap"),
    "PINE018": ("warning", "Identifier doesn't follow camelCase/SNAKE_CASE convention"),
    "PINE019": ("error", "Mixed tabs and spaces within one line's indentation"),
    "PINE020": ("error", "Block header (if/for/while/switch/else/=>) with no indented body following"),
    "PINE021": ("warning", "strategy() missing recommended sizing/commission parameters"),
    "PINE022": ("warning", "indicator()/strategy() missing an explicit overlay="),
    "PINE023": ("info", "int/int division of literals (v6 returns a fraction; v5 truncated for const int)"),
    "PINE025": ("warning", "Approaching/over line, box, label, polyline, or table limits"),
    "PINE026": ("warning", "File mixes tab-indented and space-indented lines in different places"),
    "PINE027": ("error", "indicator()/strategy() has no output-producing or order-placement call"),
    "PINE028": ("warning", "Real code appears before the //@version= pragma"),
    "PINE029": ("error", "strategy.exit() with no stop/limit/trail level (places no order)"),
    "PINE030": ("warning", "strategy.exit() mixes a relative and an absolute level of the same type"),
    "PINE031": ("warning", "Tick-denominated exit parameter given a price-denominated expression"),
    "PINE032": ("warning", "strategy.position_avg_price used with no flat-position guard"),
    "PINE033": ("error", "qty=/qty_percent= literal outside its valid range"),
    "PINE034": ("error", "strategy.exit(from_entry=) names an entry id no strategy.entry() creates"),
    "PINE035": ("warning", "Strategy places entries but never any exit/close/risk call"),
    "PINE036": ("error", "table.cell() without text_color= (Pine defaults to black — invisible on dark themes)"),
    "PINE037": ("warning", "array.new inside a per-bar block without 'var' (reallocated every execution)"),
    "PINE038": ("warning", "Drawing objects deleted and recreated inside a barstate guard (churn)"),
    "PINE039": ("warning", "Duplicate request.security() — same symbol, timeframe and lookahead"),
    "PINE040": ("warning", "plot()/plotshape()/plotchar() without a title"),
    "PINE041": ("warning", "size.large/size.huge used (design guide caps chart text at size.normal)"),
    "PINE042": ("error", "Function assigns to a global variable (compile error CE10088)"),
    "PINE043": ("error", "Function's trailing if/else branches return different types (CE10235)"),
    "PINE044": ("info", "Seconds-based timeframe used — requires a Premium TradingView plan"),
    "PINE045": ("warning", "Variable initialised to na compared with ==/!= instead of na()"),
    "PINE046": ("error", "input.*() called outside global scope (not allowed in Pine)"),
    "PINE047": ("error", "plot()/plotshape()/bgcolor()/fill() called outside global scope"),
    "PINE048": ("warning", "Approaching/over the 40 unique request.*() call limit"),
    "PINE049": ("error", "strategy.*() order call inside a function (not allowed in Pine)"),
    "PINE050": ("error", "Reassignment with := to a name that is never declared"),
    "PINE051": ("info", "Variable declared but never read (dead, or write-only)"),
    "PINE052": ("warning", "Drawing created inside a loop without the matching max_*_count"),
    "PINE053": ("warning", "Loop nest's worst-case iteration count is over budget"),
    "PINE054": ("warning", "var collection grown inside a price-dependent branch with no bar-confirmation guard"),
    "PINE055": ("error", "Function references a global declared later in the file"),
    "PINE056": ("info", "Function declared but never called"),
    "PINE057": ("warning", "Condition is constant — always true or always false"),
    "PINE058": ("error", "Name shadows a built-in namespace"),
}

# Rules --fix can repair mechanically. Every one of these has exactly one
# correct rewrite; anything needing intent stays out.
FIXABLE = {"PINE004", "PINE012", "PINE019", "PINE023", "PINE026", "PINE041"}

STRATEGY_ORDER_FUNCS = [
    "strategy.entry(", "strategy.order(", "strategy.exit(", "strategy.close(",
    "strategy.close_all(", "strategy.cancel(", "strategy.cancel_all(",
]
TRANSP_FUNCS = ["bgcolor(", "fill(", "plot(", "plotarrow(", "plotchar(", "plotshape("]
# Weighted, because they are not worth one slot each. plotcandle() and plotbar()
# each draw FOUR series, and counting them as one is how a script that looks
# comfortably under the limit turns out to be over it.
PLOT_COUNT_WEIGHTS = {
    "plot(": 1,
    "plotarrow(": 1,
    "plotchar(": 1,
    "plotshape(": 1,
    "plotbar(": 4,
    "plotcandle(": 4,
    "alertcondition(": 1,
    "bgcolor(": 1,
    "barcolor(": 1,
    "fill(": 1,
}
PLOT_COUNT_FUNCS = list(PLOT_COUNT_WEIGHTS)
DRAWING_FUNCS = {
    "line.new(": ("max_lines_count", "line"),
    "box.new(": ("max_boxes_count", "box"),
    "label.new(": ("max_labels_count", "label"),
}


class Finding:
    __slots__ = ("line", "code", "msg")

    def __init__(self, line, code, msg):
        self.line = line
        self.code = code
        self.msg = msg

    @property
    def severity(self):
        return RULES[self.code][0]


# Set by scripts/mutate_check.py to neutralise ONE rule and confirm the test
# suite notices. It is read once, here, and does nothing unless deliberately
# set — a test that cannot fail is worth nothing, and this is how we find out
# which of these rules are in that state.
MUTED_RULE = os.environ.get("PINE_LINT_MUTATE", "")


class LintResult:
    def __init__(self):
        self.findings = []

    def add(self, line_no, code, msg):
        if code and code == MUTED_RULE:
            return
        self.findings.append(Finding(line_no, code, msg))

    def by_severity(self, sev):
        return [f for f in self.findings if f.severity == sev]

    def ok(self, strict=False):
        if self.by_severity("error"):
            return False
        if strict and self.by_severity("warning"):
            return False
        return True


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------
def strip_strings_and_comments(line):
    """Remove // comments AND blank out string contents (the enclosing quotes
    are kept, so a stripped line still shows WHERE a string literal was — e.g.
    a switch arm `3 => "x"` strips to `3 => ""`, not `3 =>`). Use this for
    structural checks (brackets, keywords, param names) where string contents
    would create false positives."""
    out = []
    in_str = None
    i = 0
    while i < len(line):
        ch = line[i]
        if in_str:
            if ch == '\\' and i + 1 < len(line):
                i += 2
                continue
            if ch == in_str:
                in_str = None
                out.append(ch)
            i += 1
            continue
        if ch in ('"', "'"):
            in_str = ch
            out.append(ch)
            i += 1
            continue
        if ch == '/' and i + 1 < len(line) and line[i + 1] == '/':
            break
        out.append(ch)
        i += 1
    return ''.join(out)


def strip_comments_only(line):
    """Remove a trailing // comment but keep string contents intact. Use this
    when a check needs to know whether a string literal is present."""
    out = []
    in_str = None
    i = 0
    while i < len(line):
        ch = line[i]
        if in_str:
            out.append(ch)
            if ch == '\\' and i + 1 < len(line):
                if i + 1 < len(line):
                    out.append(line[i + 1])
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in ('"', "'"):
            in_str = ch
            out.append(ch)
            i += 1
            continue
        if ch == '/' and i + 1 < len(line) and line[i + 1] == '/':
            break
        out.append(ch)
        i += 1
    return ''.join(out)


def build_logical_statements(lines):
    """Group physical lines into logical statements by tracking paren depth
    across lines (handles the multi-line function-call style the official
    Pine style guide itself recommends). Returns a list of dicts with
    1-indexed start/end line numbers and joined raw/stripped text."""
    statements = []
    depth = 0
    cur_start = None
    cur_raw_nc = []   # comments stripped, strings intact
    cur_stripped = []  # comments + strings stripped

    for i, raw in enumerate(lines):
        raw_nc = strip_comments_only(raw)
        stripped = strip_strings_and_comments(raw)
        if cur_start is None:
            cur_start = i + 1
        cur_raw_nc.append(raw_nc)
        cur_stripped.append(stripped)
        for ch in stripped:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth = max(0, depth - 1)
        if depth == 0:
            statements.append({
                "start": cur_start,
                "end": i + 1,
                "raw_nc": "\n".join(cur_raw_nc),
                "stripped": " ".join(cur_stripped),
            })
            cur_start, cur_raw_nc, cur_stripped = None, [], []

    if cur_start is not None:
        statements.append({
            "start": cur_start,
            "end": len(lines),
            "raw_nc": "\n".join(cur_raw_nc),
            "stripped": " ".join(cur_stripped),
        })
    return statements


DECL_RE = re.compile(r'\b(indicator|strategy|library)\s*\(')


def find_declaration_statement(statements):
    """Returns the logical statement containing the indicator()/strategy()/
    library() call, or None. Declaration checks use this so a parameter name
    that merely appears in a comment elsewhere can't satisfy the check."""
    for stmt in statements:
        if DECL_RE.search(stmt["stripped"]):
            return stmt
    return None


def call_arg_text(text, func):
    """Returns the argument text of the first `func` call in `text` (balanced to
    its closing paren), or None if the call isn't found/closed."""
    idx = text.find(func)
    if idx == -1:
        return None
    start = idx + len(func)
    depth = 1
    for i in range(start, len(text)):
        ch = text[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                return text[start:i]
    return text[start:]


def split_top_level_args(arg_text):
    """Splits a call's argument text on commas at paren/bracket depth 0.

    String-aware, because a tooltip is prose and prose contains commas. Without
    this, `input.int(10, "Len", tooltip = "Raise it, or lower it")` reports four
    arguments and the tooltip is truncated at the comma."""
    args = []
    depth = 0
    current = []
    in_str = None
    escaped = False
    for ch in arg_text:
        if in_str:
            current.append(ch)
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == in_str:
                in_str = None
            continue
        if ch in ('"', "'"):
            in_str = ch
            current.append(ch)
            continue
        if ch in '([':
            depth += 1
        elif ch in ')]':
            depth -= 1
        if ch == ',' and depth == 0:
            args.append(''.join(current).strip())
            current = []
            continue
        current.append(ch)
    tail = ''.join(current).strip()
    if tail:
        args.append(tail)
    return args


def named_arg(args, name):
    """Returns the value expression for `name=` among split args, else None."""
    pat = re.compile(r'^' + re.escape(name) + r'\s*=\s*(?!=)(.*)$', re.DOTALL)
    for a in args:
        m = pat.match(a)
        if m:
            return m.group(1).strip()
    return None


def positional_args(args):
    """Returns the args that are not `name=value` form, in order."""
    return [a for a in args if not re.match(r'^[a-zA-Z_]\w*\s*=(?!=)', a)]


def statements_calling(statements, func):
    """Yields (stmt, arg_text_with_strings_intact) for each logical statement
    containing `func`."""
    for stmt in statements:
        if func in stmt["stripped"]:
            arg_text = call_arg_text(strip_comments_only_multi(stmt["raw_nc"]), func)
            if arg_text is not None:
                yield stmt, arg_text


def strip_comments_only_multi(text):
    """strip_comments_only() applied per line, rejoined with spaces — turns a
    multi-line logical statement into one line for argument parsing."""
    return " ".join(strip_comments_only(l) for l in text.split("\n"))


def parse_suppressions(lines):
    """Returns (file_wide_codes: set, next_line_map: {line_no: set(codes)},
    same_line_map: {line_no: set(codes)})."""
    file_wide = set()
    next_line = {}
    same_line = {}
    for i, raw in enumerate(lines):
        m_next = re.search(r'//\s*pine-lint-disable-next-line\s+([\w,\s]+)\s*$', raw)
        m_same = re.search(r'//\s*pine-lint-disable-line\s+([\w,\s]+)\s*$', raw)
        m_file = re.search(r'//\s*pine-lint-disable\s+([\w,\s]+)\s*$', raw)
        # Check the more specific directives first since their text also
        # loosely matches the generic file-wide pattern's tail.
        if m_next:
            codes = {c.strip() for c in m_next.group(1).split(",") if c.strip()}
            next_line[i + 2] = next_line.get(i + 2, set()) | codes
        elif m_same:
            codes = {c.strip() for c in m_same.group(1).split(",") if c.strip()}
            same_line[i + 1] = same_line.get(i + 1, set()) | codes
        elif m_file:
            codes = {c.strip() for c in m_file.group(1).split(",") if c.strip()}
            file_wide |= codes
    return file_wide, next_line, same_line


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------
def check_version_pragma(lines, result):
    """Per TradingView's own Script structure docs: the //@version= annotation
    is 'syntactically correct anywhere' but 'much more useful to readers when
    it appears at the top' — so only comments/blank lines before it are fully
    fine; real code before it is a (soft) style warning, not a hard error."""
    if not lines:
        result.add(1, "PINE001", "File is empty.")
        return None
    version = None
    version_line_idx = None
    saw_code_before_version = False
    for i, raw in enumerate(lines):
        trimmed = raw.strip()
        if not trimmed:
            continue
        m = re.match(r'//@version=(\d+)\s*$', trimmed)
        if m:
            version = int(m.group(1))
            version_line_idx = i
            break
        if trimmed.startswith('//'):
            continue
        saw_code_before_version = True
    if version_line_idx is None:
        result.add(1, "PINE001", "No //@version= pragma found anywhere in the file (Pine silently "
                                  "assumes v1 without one, which disables modern syntax).")
        return None
    if saw_code_before_version:
        result.add(version_line_idx + 1, "PINE028",
                    "Real code appears before the //@version= pragma. This is syntactically valid, "
                    "but TradingView's style guide recommends placing it at the top (after any license "
                    "comment) for readability.")
    return version


def check_declaration(text, statements, result):
    has_indicator = bool(re.search(r'\bindicator\s*\(', text))
    has_strategy = bool(re.search(r'\bstrategy\s*\(', text))
    has_library = bool(re.search(r'\blibrary\s*\(', text))
    if not (has_indicator or has_strategy or has_library):
        result.add(0, "PINE002", "No indicator(), strategy(), or library() declaration found.")
        return
    # Scope the parameter search to the declaration call itself — a whole-file
    # substring test is satisfied by a mention in a comment.
    decl = find_declaration_statement(statements)
    decl_text = decl["stripped"] if decl else text
    if (has_indicator or has_strategy) and "overlay=" not in decl_text and "overlay =" not in decl_text:
        result.add(0, "PINE022", "indicator()/strategy() doesn't set overlay= explicitly.")
    if has_strategy:
        missing = [p for p in ("default_qty_type", "default_qty_value", "commission_",
                               "initial_capital", "slippage")
                   if p not in decl_text]
        if missing:
            result.add(0, "PINE021",
                        "strategy() call doesn't set " + ", ".join(missing) + " — engine defaults "
                        "will silently shape backtest results (v6 defaults margin_long/short to 100, "
                        "so at least funds/margin are realistic by default, but sizing/commission still "
                        "need explicit values for a meaningful backtest). initial_capital and slippage "
                        "change every number the Strategy Tester reports, so leaving them implicit "
                        "means the published backtest isn't reproducible.")


OUTPUT_FUNCS = [
    "plot(", "plotshape(", "plotcandle(", "plotbar(", "plotchar(", "plotarrow(",
    "barcolor(", "line.new(", "label.new(", "table.new(", "box.new(", "polyline.new(",
    "log.info(", "log.warning(", "log.error(", "alert(", "bgcolor(", "fill(",
]
STRATEGY_OUTPUT_FUNCS = OUTPUT_FUNCS + [
    "strategy.entry(", "strategy.order(", "strategy.close(", "strategy.close_all(", "strategy.exit(",
]


def check_has_output(text, result):
    """Per TradingView's Script structure docs: indicators must call at least
    one output-producing function and strategies at least one order-placement
    or output function, or the script is a compile error."""
    has_indicator = bool(re.search(r'\bindicator\s*\(', text))
    has_strategy = bool(re.search(r'\bstrategy\s*\(', text))
    has_library = bool(re.search(r'\blibrary\s*\(', text))
    if has_library:
        return
    if has_indicator and not any(f in text for f in OUTPUT_FUNCS):
        result.add(0, "PINE027",
                    "indicator() script has no output-producing call (plot/plotshape/barcolor/"
                    "line.new/log.info/alert/etc.) — Pine requires at least one, or the script "
                    "won't compile.")
    if has_strategy and not any(f in text for f in STRATEGY_OUTPUT_FUNCS):
        result.add(0, "PINE027",
                    "strategy() script has no order-placement or output call (strategy.entry/order/"
                    "close/exit, plot, etc.) — Pine requires at least one, or the script won't compile.")


def check_balanced_delimiters(lines, result):
    pairs = {'(': ')', '[': ']'}
    stack = []
    for i, line in enumerate(lines):
        code = strip_strings_and_comments(line)
        for ch in code:
            if ch in pairs:
                stack.append((ch, i + 1))
            elif ch in pairs.values():
                if not stack:
                    result.add(i + 1, "PINE003", f"Unmatched closing '{ch}'.")
                    continue
                open_ch, _ = stack.pop()
                if pairs[open_ch] != ch:
                    result.add(i + 1, "PINE003", f"Mismatched '{open_ch}' closed with '{ch}'.")
    for open_ch, line_no in stack:
        result.add(line_no, "PINE003", f"Unclosed '{open_ch}' — never closed before end of file.")


def check_deprecated_syntax(lines, result):
    for i, raw_line in enumerate(lines):
        line = strip_strings_and_comments(raw_line)
        if re.search(r'\bstudy\s*\(', line):
            result.add(i + 1, "PINE004", "study() is deprecated — use indicator() instead.")
        if re.search(r'(?<!request\.)\bsecurity\s*\(', line):
            result.add(i + 1, "PINE004", "security() is deprecated — use request.security() instead.")


def check_security_lookahead(statements, result, cfg):
    if not cfg.get("warn_on_security_lookahead", True):
        return
    for stmt in statements:
        if 'request.security(' in stmt["stripped"] and 'lookahead=' not in stmt["stripped"]:
            result.add(stmt["start"], "PINE006",
                        "request.security() without an explicit lookahead= argument — verify this "
                        "isn't introducing repainting (usually want lookahead=barmerge.lookahead_off).")


LOCAL_DECL_RE = re.compile(
    r'^\s*(?:int|float|bool|string|color|array(?:<[^>]*>)?|matrix(?:<[^>]*>)?|'
    r'map(?:<[^>]*>)?)?\s*([a-zA-Z_]\w*)\s*=(?![=>])'
)


def check_var_accumulator(lines, result):
    """PINE005 only makes sense at GLOBAL scope: `total = 0` then `total := total + x`
    resets every bar. A name declared inside a local scope (function body, if/for
    block — i.e. at indent > 0) is an ordinary local builder, where `var` would be
    wrong, so those are exempt."""
    var_declared = set()
    local_declared = set()
    for i, raw_line in enumerate(lines):
        line = strip_strings_and_comments(raw_line)
        m_decl = re.match(r'\s*var(?:ip)?\s+\w*\s*(\w+)\s*=', line)
        if m_decl:
            var_declared.add(m_decl.group(1))
            continue
        m_local = LOCAL_DECL_RE.match(line)
        if m_local and indent_width(raw_line) > 0:
            local_declared.add(m_local.group(1))
        m_self = re.match(r'\s*(\w+)\s*:?=\s*\1\s*[\+\-\*/]', line)
        if m_self:
            name = m_self.group(1)
            if name not in var_declared and name not in local_declared:
                result.add(i + 1, "PINE005",
                            f"'{name}' looks like a running accumulator ('{name} = {name} + ...') but "
                            f"wasn't declared with 'var' — it will reset every bar. If intentional, ignore.")


def check_line_length(lines, result, cfg):
    max_len = cfg.get("max_line_length", 120)
    for i, line in enumerate(lines):
        length = len(line.rstrip('\n'))
        if length > max_len:
            result.add(i + 1, "PINE008", f"Line exceeds {max_len} characters ({length}).")


def check_inputs_have_titles(statements, result):
    input_re = re.compile(r'\binput\.(int|float|bool|string|source|color|timeframe|symbol|price|text_area|enum)\s*\(')
    for stmt in statements:
        if not input_re.search(stmt["stripped"]):
            continue
        has_title_kw = bool(re.search(r'\btitle\s*=', stmt["stripped"]))
        has_quoted_string = bool(re.search(r'"[^"]*"', stmt["raw_nc"])) or bool(re.search(r"'[^']*'", stmt["raw_nc"]))
        if not has_title_kw and not has_quoted_string:
            result.add(stmt["start"], "PINE007",
                        "input.*() call has no title= and no quoted string argument — the settings "
                        "panel will show a blank/generic label for this input.")


def check_when_removed(statements, result):
    for stmt in statements:
        if any(f in stmt["stripped"] for f in STRATEGY_ORDER_FUNCS) and re.search(r'\bwhen\s*=', stmt["stripped"]):
            result.add(stmt["start"], "PINE010",
                        "when= is removed in Pine v6 — wrap this call in an `if` statement instead "
                        "(e.g. `if condition` then `strategy.entry(...)` indented below).")


# Exit-level parameters. Absolute ones are in PRICE, relative ones in TICKS.
EXIT_LEVEL_PARAMS = ("stop", "loss", "limit", "profit", "trail_price", "trail_points")
# (relative, absolute) pairs that address the same exit type.
EXIT_LEVEL_PAIRS = (("profit", "limit"), ("loss", "stop"), ("trail_points", "trail_price"))
# Parameters denominated in ticks rather than price.
TICK_PARAMS = ("loss", "profit", "trail_points", "trail_offset")
TICK_HINTS = ("syminfo.mintick", "mintick", "syminfo.pointvalue")


def check_exit_has_level(statements, result):
    """PINE029 — an exit whose level arguments are all absent places no order,
    which silently means 'no risk management' rather than an error."""
    for stmt, arg_text in statements_calling(statements, "strategy.exit("):
        args = split_top_level_args(arg_text)
        if not any(named_arg(args, p) is not None for p in EXIT_LEVEL_PARAMS):
            result.add(stmt["start"], "PINE029",
                        "strategy.exit() sets none of stop/loss/limit/profit/trail_price/"
                        "trail_points — an exit command with no level places no order at all, so "
                        "this position has no stop and no target.")


def check_exit_level_pairs(statements, result):
    """PINE030 — mixing a relative and an absolute level of the same type."""
    for stmt, arg_text in statements_calling(statements, "strategy.exit("):
        args = split_top_level_args(arg_text)
        for rel, absolute in EXIT_LEVEL_PAIRS:
            if named_arg(args, rel) is not None and named_arg(args, absolute) is not None:
                result.add(stmt["start"], "PINE030",
                            f"strategy.exit() sets both '{rel}' (relative, ticks) and "
                            f"'{absolute}' (absolute, price) for the same exit type. In v5 the "
                            f"absolute level always won; in v6 whichever triggers FIRST wins, so a "
                            f"ported v5 strategy exits differently now. Set only one.")


def check_exit_tick_params(statements, result):
    """PINE031 — a tick-denominated parameter handed a price-shaped expression."""
    for stmt, arg_text in statements_calling(statements, "strategy.exit("):
        args = split_top_level_args(arg_text)
        for param in TICK_PARAMS:
            value = named_arg(args, param)
            if value is None or value == "na":
                continue
            if any(hint in value for hint in TICK_HINTS):
                continue
            if re.fullmatch(r'-?\d+', value.strip()):
                continue
            result.add(stmt["start"], "PINE031",
                        f"strategy.exit(...{param}=...) is denominated in TICKS, not price. "
                        f"'{value.strip()}' looks like a price distance — convert it with "
                        f"int(priceDistance / syminfo.mintick), or use the absolute price "
                        f"parameter (stop/limit/trail_price) instead.")


POSITION_GUARDS = (
    "strategy.position_size >", "strategy.position_size<", "strategy.position_size <",
    "strategy.position_size>", "strategy.position_size !=", "strategy.position_size!=",
    "strategy.position_size ==", "strategy.position_size==",
    "na(strategy.position_avg_price)", "strategy.opentrades",
)


def check_position_avg_price_guard(text, result):
    """PINE032 — file-level check that a flat-position guard exists somewhere."""
    if "strategy.position_avg_price" not in text:
        return
    if any(guard in text for guard in POSITION_GUARDS):
        return
    result.add(0, "PINE032",
                "strategy.position_avg_price is used but nothing in this file guards on "
                "strategy.position_size / strategy.opentrades. While flat, position_avg_price is "
                "na, so any stop or target derived from it is na on those bars and the resulting "
                "exit order silently does nothing.")


def check_order_qty_range(statements, result):
    """PINE033 — literal qty/qty_percent outside its valid range."""
    for stmt in statements:
        if not any(f in stmt["stripped"] for f in STRATEGY_ORDER_FUNCS):
            continue
        for m in re.finditer(r'\bqty(_percent)?\s*=\s*(-?\d+(?:\.\d+)?)\b', stmt["stripped"]):
            is_percent = m.group(1) is not None
            value = float(m.group(2))
            if is_percent and not (0 < value <= 100):
                result.add(stmt["start"], "PINE033",
                            f"qty_percent={m.group(2)} is outside the valid 0-100 range — "
                            f"the partial-exit order will be rejected or close nothing.")
            elif not is_percent and value <= 0:
                result.add(stmt["start"], "PINE033",
                            f"qty={m.group(2)} is not a positive size — the order places nothing.")


def check_exit_from_entry(statements, result):
    """PINE034 — an exit whose from_entry names an id no entry creates. Skipped
    entirely if any entry id is a non-literal expression, since ids can be
    computed at runtime and this rule is error-severity."""
    entry_ids = set()
    for func in ("strategy.entry(", "strategy.order("):
        for stmt, arg_text in statements_calling(statements, func):
            args = split_top_level_args(arg_text)
            value = named_arg(args, "id")
            if value is None:
                pos = positional_args(args)
                value = pos[0] if pos else None
            if value is None:
                return
            m = re.fullmatch(r'"([^"]*)"|\'([^\']*)\'', value.strip())
            if not m:
                return          # dynamic id — can't reason about it, bail out
            entry_ids.add(m.group(1) if m.group(1) is not None else m.group(2))
    if not entry_ids:
        return
    for stmt, arg_text in statements_calling(statements, "strategy.exit("):
        args = split_top_level_args(arg_text)
        value = named_arg(args, "from_entry")
        if value is None:
            pos = positional_args(args)
            value = pos[1] if len(pos) > 1 else None
        if value is None:
            continue
        m = re.fullmatch(r'"([^"]*)"|\'([^\']*)\'', value.strip())
        if not m:
            continue
        name = m.group(1) if m.group(1) is not None else m.group(2)
        if name not in entry_ids:
            result.add(stmt["start"], "PINE034",
                        f"strategy.exit(from_entry=\"{name}\") names an entry id that no "
                        f"strategy.entry()/strategy.order() in this file creates "
                        f"(found: {', '.join(sorted(entry_ids))}). The exit attaches to nothing "
                        f"and never fires.")


EXIT_MECHANISMS = ("strategy.exit(", "strategy.close(", "strategy.close_all(", "strategy.risk.")


def check_entries_have_exits(text, result):
    """PINE035 — entries with no exit mechanism anywhere in the file."""
    if not ("strategy.entry(" in text or "strategy.order(" in text):
        return
    if any(mech in text for mech in EXIT_MECHANISMS):
        return
    result.add(0, "PINE035",
                "This strategy places entries but never calls strategy.exit(), strategy.close(), "
                "strategy.close_all(), or a strategy.risk.* rule — positions are only ever closed "
                "by an opposite entry, so no trade has a defined risk.")


# ---------------------------------------------------------------------------
# Visual / performance rules (PINE036-PINE041)
# ---------------------------------------------------------------------------
TABLE_CELL_FUNCS = ("table.cell(", ".cell(")


def check_table_cell_text_color(statements, result):
    """PINE036 — a cell without text_color= renders with Pine's default, which is
    black. Over a dark table background or a dark chart that text is invisible.

    Both call forms are handled: table.cell(id, col, row, text, ...) takes the
    text as the 4th positional argument, while the method form
    myTable.cell(col, row, text, ...) takes it as the 3rd."""
    seen = set()
    for func in TABLE_CELL_FUNCS:
        text_index = 3 if func == "table.cell(" else 2
        for stmt, arg_text in statements_calling(statements, func):
            if stmt["start"] in seen:
                continue
            seen.add(stmt["start"])
            args = split_top_level_args(arg_text)
            if named_arg(args, "text_color") is not None:
                continue
            text_value = named_arg(args, "text")
            if text_value is None:
                positional = positional_args(args)
                if len(positional) <= text_index:
                    continue          # no text argument — a spacer cell
                text_value = positional[text_index]
            # An empty string literal is a deliberate spacer and needs no colour.
            if re.fullmatch(r'""|\'\'', text_value.strip()):
                continue
            result.add(stmt["start"], "PINE036",
                        "table cell sets no text_color= — Pine defaults cell text to black, so "
                        "this cell is invisible on a dark table background or a dark chart. Set "
                        "text_color= explicitly on every cell that shows text.")


ARRAY_NEW_RE = re.compile(r'\barray\.new(?:<[^>]*>)?\s*\(|\bmatrix\.new(?:<[^>]*>)?\s*\(')
FUNC_DECL_RE = re.compile(r'^[a-zA-Z_]\w*\s*\([^)]*\)\s*=>')


def check_array_alloc_in_block(lines, result):
    """PINE037 — array.new inside an indented block that is not a function body.
    Such a block re-runs every bar (or every realtime tick under barstate.islast),
    so the allocation is repeated; `var` + array.fill() reuses one buffer."""
    stripped = [strip_strings_and_comments(l) for l in lines]
    # Track which indented regions belong to a user function body, where a local
    # array is a normal temporary rather than per-bar churn.
    in_function_until_indent = None
    for i, line in enumerate(stripped):
        if not line.strip():
            continue
        indent = indent_width(lines[i])
        if in_function_until_indent is not None and indent <= in_function_until_indent:
            in_function_until_indent = None
        if indent == 0 and FUNC_DECL_RE.match(line.strip()):
            in_function_until_indent = 0
            continue
        if in_function_until_indent is not None or indent == 0:
            continue
        if not ARRAY_NEW_RE.search(line):
            continue
        if re.match(r'\s*var(?:ip)?\s', line):
            continue
        result.add(i + 1, "PINE037",
                    "array.new/matrix.new inside an indented block without 'var' — this block "
                    "re-runs every bar (every realtime tick inside a barstate.islast guard), so "
                    "the buffer is reallocated each time. Declare it once with 'var' and reset it "
                    "with array.fill() instead.")


DRAWING_TYPES = ("line", "box", "label", "polyline")


def check_drawing_churn(lines, result):
    """PINE038 — deleting and recreating the same drawing type inside a barstate
    guard. Updating a `var` object with .set_*() is far cheaper and doesn't flicker."""
    stripped = [strip_strings_and_comments(l) for l in lines]
    n = len(lines)
    for i in range(n):
        if "barstate.islast" not in stripped[i] and "barstate.isrealtime" not in stripped[i]:
            continue
        if not re.search(r'\bif\b', stripped[i]):
            continue
        guard_indent = indent_width(lines[i])
        body = []
        j = i + 1
        while j < n:
            if not stripped[j].strip():
                j += 1
                continue
            if indent_width(lines[j]) <= guard_indent:
                break
            body.append(stripped[j])
            j += 1
        block = "\n".join(body)
        for kind in DRAWING_TYPES:
            if f"{kind}.new(" in block and f"{kind}.delete(" in block:
                result.add(i + 1, "PINE038",
                            f"this barstate block both deletes and recreates {kind} objects, so "
                            f"they churn on every realtime tick. Create them once with 'var' and "
                            f"update them with {kind}.set_*() instead — cheaper and no flicker.")


def check_duplicate_security(statements, result):
    """PINE039 — two request.security() calls sharing symbol, timeframe and
    lookahead can be merged into one tuple request, saving a whole HTF series
    evaluation and one slot against the 40-unique-call cap."""
    seen = {}
    for stmt, arg_text in statements_calling(statements, "request.security("):
        args = split_top_level_args(arg_text)
        positional = positional_args(args)
        symbol = named_arg(args, "symbol")
        if symbol is None:
            symbol = positional[0] if positional else None
        timeframe = named_arg(args, "timeframe")
        if timeframe is None:
            timeframe = positional[1] if len(positional) > 1 else None
        lookahead = named_arg(args, "lookahead") or "(default)"
        if symbol is None or timeframe is None:
            continue
        key = (symbol.strip(), timeframe.strip(), lookahead.strip())
        if key in seen:
            result.add(stmt["start"], "PINE039",
                        f"request.security({key[0]}, {key[1]}, ... lookahead={key[2]}) duplicates "
                        f"the call on line {seen[key]} — same symbol, timeframe and lookahead. "
                        f"Merge them into one call returning a tuple to save an HTF evaluation.")
        else:
            seen[key] = stmt["start"]


TITLED_PLOT_FUNCS = ("plot(", "plotshape(", "plotchar(", "plotarrow(")


def check_plot_has_title(statements, result):
    """PINE040 — an untitled plot shows as 'Plot' in the settings panel, the data
    window and the status line. Mirrors PINE007 for inputs."""
    seen = set()
    for func in TITLED_PLOT_FUNCS:
        for stmt, arg_text in statements_calling(statements, func):
            if stmt["start"] in seen:
                continue
            args = split_top_level_args(arg_text)
            if named_arg(args, "title") is not None:
                continue
            positional = positional_args(args)
            has_title_positional = (
                len(positional) > 1 and re.match(r'^["\']', positional[1].strip()))
            if has_title_positional:
                continue
            seen.add(stmt["start"])
            result.add(stmt["start"], "PINE040",
                        f"{func[:-1]}() has no title — it will appear as an unnamed entry in the "
                        f"settings panel, data window and status line. Pass a title as the second "
                        f"positional argument or with title=.")


BIG_SIZE_RE = re.compile(r'\bsize\.(large|huge)\b')


def check_oversized_text(lines, result):
    """PINE041 — references/design-system.md caps chart text at size.normal;
    anything larger clips or wraps badly at real panel widths."""
    for i, raw in enumerate(lines):
        line = strip_strings_and_comments(raw)
        m = BIG_SIZE_RE.search(line)
        if m:
            result.add(i + 1, "PINE041",
                        f"size.{m.group(1)} is larger than references/design-system.md allows for "
                        f"chart text — at real panel widths it clips or wraps. Use size.normal for "
                        f"a headline value and size.small elsewhere.")


def iter_function_bodies(lines):
    """Yields (decl_line_index, [(line_index, text), ...]) for each user function
    declared at global scope, with its indented body."""
    stripped = [strip_strings_and_comments(l) for l in lines]
    n = len(lines)
    for i in range(n):
        text = stripped[i]
        if not text.strip() or indent_width(lines[i]) != 0:
            continue
        if not FUNC_DECL_RE.match(text.strip()):
            continue
        body = []
        j = i + 1
        while j < n:
            if not stripped[j].strip():
                j += 1
                continue
            if indent_width(lines[j]) == 0:
                break
            body.append((j, stripped[j]))
            j += 1
        if body:
            yield i, body


GLOBAL_DECL_RE = re.compile(
    r'^\s*(?:var(?:ip)?\s+)?(?:int|float|bool|string|color|label|line|box|table|'
    r'array(?:<[^>]*>)?|matrix(?:<[^>]*>)?|map(?:<[^>]*>)?)?\s*([a-zA-Z_]\w*)\s*(?::=|=)(?![=>])'
)
ASSIGN_RE = re.compile(r'^\s*([a-zA-Z_]\w*)\s*(?::=|\+=|-=|\*=|/=|%=)')


def check_global_mutation_in_function(lines, result):
    """PINE042 — Pine forbids a function from modifying a variable declared at
    global scope. It is a hard compile error (CE10088) that no other rule here
    catches, and the assertion-counter idiom walks straight into it."""
    globals_declared = set()
    for i, raw in enumerate(lines):
        if indent_width(raw) != 0:
            continue
        m = GLOBAL_DECL_RE.match(strip_strings_and_comments(raw))
        if m:
            globals_declared.add(m.group(1))
    if not globals_declared:
        return
    for decl_idx, body in iter_function_bodies(lines):
        params = set(re.findall(r'([a-zA-Z_]\w*)\s*(?:,|\))', body and lines[decl_idx] or ""))
        locals_here = set()
        for line_idx, text in body:
            m_local = LOCAL_DECL_RE.match(text)
            if m_local:
                locals_here.add(m_local.group(1))
            m_assign = ASSIGN_RE.match(text)
            if not m_assign:
                continue
            name = m_assign.group(1)
            if name in locals_here or name in params:
                continue
            if name not in globals_declared:
                continue
            result.add(line_idx + 1, "PINE042",
                        f"'{name}' is declared at global scope, and Pine does not allow a function "
                        f"to modify it (compile error CE10088). Return the value and let the caller "
                        f"apply it instead.")


CONSTRUCTOR_RE = re.compile(r'\b\w+\.new\s*\(')


def check_function_branch_types(lines, result):
    """PINE043 — when an if/else is a function's LAST statement it becomes the
    return value, so both branches must yield the same type (CE10235). The
    classic break is one branch ending in an assignment and the other in a
    drawing constructor, which yields `series int` vs `series label`."""
    for _decl_idx, body in iter_function_bodies(lines):
        last_idx = body[-1][0]
        else_pos = None
        for pos, (line_idx, text) in enumerate(body):
            if re.match(r'^\s*else\s*$', text):
                else_pos = pos
        if else_pos is None or else_pos == len(body) - 1:
            continue
        if_last = body[else_pos - 1][1] if else_pos > 0 else ""
        else_last = body[-1][1]
        if body[-1][0] != last_idx:
            continue
        if_is_assign = bool(ASSIGN_RE.match(if_last))
        else_is_ctor = bool(CONSTRUCTOR_RE.search(else_last))
        else_is_assign = bool(ASSIGN_RE.match(else_last))
        if_is_ctor = bool(CONSTRUCTOR_RE.search(if_last))
        if (if_is_assign and else_is_ctor) or (else_is_assign and if_is_ctor):
            result.add(body[else_pos][0] + 1, "PINE043",
                        "this if/else is the function's last statement, so it is the return value "
                        "and both branches must have the same type — but one ends in an assignment "
                        "and the other in a .new() constructor (CE10235). End the function with a "
                        "single plain expression instead.")


SECONDS_TF_RE = re.compile(r'["\'](\d+)S["\']')


def check_seconds_timeframe(lines, result):
    """PINE044 — TradingView serves seconds-based timeframes only to Premium and
    higher plans, and requesting one on a lower plan fails the WHOLE script, not
    just that call. Advisory (info) because it is a legitimate choice when the
    audience is known — but it should be a deliberate, gated one."""
    for i, raw in enumerate(lines):
        line = strip_comments_only(raw)
        m = SECONDS_TF_RE.search(line)
        if m:
            value = m.group(1)
            result.add(i + 1, "PINE044",
                        f'"{value}S" is a seconds-based timeframe. TradingView serves those only '
                        f"to Premium and higher plans, and asking for one on a lower plan fails "
                        f"the entire script rather than that single call. Gate it behind an input "
                        f"that defaults to OFF and falls back to a minute-based resolution.")
            return


VAR_NA_DECL_RE = re.compile(
    r'^\s*var(?:ip)?\s+(?:int|float|bool|string|color|label|line|box|table)?\s*'
    r'([a-zA-Z_]\w*)\s*=\s*na\s*$'
)


def check_na_comparison(lines, result):
    """PINE045 — a variable initialised to `na` and then tested with `==`/`!=`.
    Pine does not compare reliably against na, so the test silently never
    matches and whatever it guards never runs. Use na(x) instead."""
    na_vars = {}
    for i, raw in enumerate(lines):
        m = VAR_NA_DECL_RE.match(strip_strings_and_comments(raw))
        if m:
            na_vars[m.group(1)] = i + 1
    if not na_vars:
        return
    text = chr(10).join(strip_strings_and_comments(l) for l in lines)
    for name, decl_line in na_vars.items():
        if re.search(r'\bna\s*\(\s*' + re.escape(name) + r'\s*\)', text):
            continue      # the file already guards this one properly
        for i, raw in enumerate(lines):
            line = strip_strings_and_comments(raw)
            if re.search(r'\b' + re.escape(name) + r'\s*[=!]=', line):
                result.add(i + 1, "PINE045",
                            f"'{name}' is initialised to na (line {decl_line}) and compared with "
                            f"==/!=. Pine does not compare reliably against na, so this test never "
                            f"matches on the first pass and whatever it guards silently never runs. "
                            f"Use na({name}) for the na case.")
                break


# The leading (?<![.\w]) matters: these are all bare global functions, never
# members of a namespace. Without it `array.fill(` matches the `fill(` in the
# plot family and every buffer reset gets flagged as an illegal plot call.
GLOBAL_ONLY_INPUT_RE = re.compile(r'(?<![.\w])input\s*(?:\.\s*\w+\s*)?\(')
GLOBAL_ONLY_PLOT_RE = re.compile(
    r'(?<![.\w])(plot|plotshape|plotchar|plotarrow|plotbar|plotcandle|bgcolor|barcolor|fill|'
    r'hline|alertcondition)\s*\('
)
STRATEGY_CALL_RE = re.compile(
    r'(?<![.\w])strategy\s*\.\s*(entry|order|exit|close|close_all|cancel|cancel_all)\s*\(')


def _indented_code_lines(lines, statements):
    """Yields (index, stripped_text) for lines that are inside SOME indented
    block — i.e. not at global scope. Continuation lines of a wrapped global
    statement are excluded, since those are still global scope."""
    stmt_start = {}
    for stmt in statements:
        for ln in range(stmt["start"], stmt["end"] + 1):
            stmt_start[ln] = stmt["start"]
    for i, raw in enumerate(lines):
        text = strip_strings_and_comments(raw)
        if not text.strip():
            continue
        start_line = stmt_start.get(i + 1, i + 1)
        if indent_width(lines[start_line - 1]) == 0:
            continue          # statement begins at global scope
        yield i, text


def check_input_scope(lines, statements, result):
    """PINE046 — input.*() must be called at global scope. Inside a function,
    an if, or a loop it is a compile error, and the message TradingView gives
    ("cannot use ... in local scope") does not say which call caused it."""
    for i, text in _indented_code_lines(lines, statements):
        if GLOBAL_ONLY_INPUT_RE.search(text):
            result.add(i + 1, "PINE046",
                        "input.*() is only allowed at global scope — not inside a function, "
                        "an if, or a loop. Declare the input at the top level and pass the "
                        "value in.")
            return


def check_plot_scope(lines, statements, result):
    """PINE047 — the plot family is global-scope-only too. The usual mistake is
    putting plot() inside `if showX` instead of passing na through it."""
    for i, text in _indented_code_lines(lines, statements):
        m = GLOBAL_ONLY_PLOT_RE.search(text)
        if m:
            name = m.group(1)
            result.add(i + 1, "PINE047",
                        f"{name}() is only allowed at global scope. To make it conditional, "
                        f"keep the call at the top level and feed it na — e.g. "
                        f"plot(showIt ? value : na) — rather than wrapping it in an if.")
            return


def check_strategy_call_scope(lines, result):
    """PINE049 — strategy order calls cannot live inside a user function."""
    for _decl_idx, body in iter_function_bodies(lines):
        for line_idx, text in body:
            m = STRATEGY_CALL_RE.search(text)
            if m:
                result.add(line_idx + 1, "PINE049",
                            f"strategy.{m.group(1)}() cannot be called from inside a function. "
                            f"Return the decision from the function and place the order at "
                            f"global scope.")
                return


def check_request_count(statements, result, cfg):
    """PINE048 — TradingView caps a script at 40 unique request.*() calls (64 on
    Ultimate). Identical calls reuse one series, so this counts DISTINCT
    argument lists, which is what actually consumes the budget."""
    seen = set()
    last_line = 0
    for stmt in statements:
        for m in re.finditer(r'\brequest\.\w+\s*\(', stmt["stripped"]):
            flat = strip_comments_only_multi(stmt["raw_nc"])
            func = m.group(0)
            args = call_arg_text(flat, func)
            key = (func, re.sub(r'\s+', '', args or str(stmt["start"])))
            seen.add(key)
            last_line = max(last_line, stmt["start"])
    if not seen:
        return
    cap = cfg.get("max_requests", 40)
    ratio = cfg.get("request_warn_ratio", 0.75)
    count = len(seen)
    if count > cap:
        result.add(last_line, "PINE048",
                    f"{count} unique request.*() calls found, over the {cap}-call limit "
                    f"(64 on the Ultimate plan). Merge calls that share a symbol and "
                    f"timeframe into one tuple request.")
    elif count > cap * ratio:
        result.add(last_line, "PINE048",
                    f"{count} unique request.*() calls found, approaching the {cap}-call "
                    f"limit. Identical calls reuse one series, but each distinct argument "
                    f"list costs a slot.")


def check_transp_removed(statements, result):
    for stmt in statements:
        if any(f in stmt["stripped"] for f in TRANSP_FUNCS) and re.search(r'\btransp\s*=', stmt["stripped"]):
            result.add(stmt["start"], "PINE011",
                        "transp= is removed in Pine v6 — use color.new(color, transparency) instead "
                        "and pass the result to color=.")


def check_linewidth_minimum(statements, result):
    for stmt in statements:
        for m in re.finditer(r'\blinewidth\s*=\s*(-?\d+)', stmt["stripped"]):
            if int(m.group(1)) < 1:
                result.add(stmt["start"], "PINE012",
                            f"linewidth={m.group(1)} is below the v6 minimum of 1 (v5 silently clamped "
                            f"this visually; v6 raises a compile error).")


def indent_width(raw_line):
    ws = raw_line[:len(raw_line) - len(raw_line.lstrip(' \t'))]
    return len(ws.expandtabs(4))


def check_switch_default(lines, result):
    stripped_lines = [strip_strings_and_comments(l) for l in lines]
    n = len(lines)
    for i in range(n):
        trimmed = stripped_lines[i].strip()
        if not re.search(r'\bswitch\b', trimmed):
            continue
        header_indent = indent_width(lines[i])
        j = i + 1
        found_default = False
        found_any_body = False
        while j < n:
            candidate = stripped_lines[j]
            if not candidate.strip():
                j += 1
                continue
            cand_indent = indent_width(lines[j])
            if cand_indent <= header_indent:
                break
            found_any_body = True
            if candidate.strip().startswith("=>"):
                found_default = True
            j += 1
        if found_any_body and not found_default:
            result.add(i + 1, "PINE013",
                        "switch statement has no default '=>' arm — required in Pine v6 (v5 allowed "
                        "omitting it). Add a bare `=> <value>` as the last arm.")


def check_history_on_literal(lines, result):
    patterns = [
        re.compile(r'\b(true|false)\s*\['),
        re.compile(r'\bcolor\.[a-zA-Z_]\w*\s*\['),
        re.compile(r'(?<![\w.])\d+(\.\d+)?\s*\['),
        re.compile(r'"[^"]*"\s*\['),
        re.compile(r"'[^']*'\s*\["),
    ]
    for i, raw in enumerate(lines):
        raw_nc = strip_comments_only(raw)
        for pat in patterns:
            if pat.search(raw_nc):
                result.add(i + 1, "PINE014",
                            "History-referencing operator [] applied to what looks like a literal or "
                            "built-in constant — invalid in Pine v6 (only variables/series can be "
                            "history-referenced now).")
                break


def check_duplicate_named_params(statements, result):
    arg_re = re.compile(r'(?<![:<>=!])\b([a-zA-Z_]\w*)\s*=(?![=>])')
    for stmt in statements:
        text = stmt["stripped"]
        seen = {}
        for m in arg_re.finditer(text):
            depth = text[:m.start()].count('(') - text[:m.start()].count(')')
            key = (m.group(1), depth)
            seen[key] = seen.get(key, 0) + 1
        dups = sorted({name for (name, depth), count in seen.items() if count > 1 and depth >= 1})
        for name in dups:
            result.add(stmt["start"], "PINE015",
                        f"Parameter '{name}' appears more than once in the same function call — this "
                        f"only used the first value (with a warning) in v5; it's a compile error in v6.")


def check_timeframe_period_compare(lines, result):
    pat = re.compile(r'timeframe\.period\s*==\s*"([A-Za-z]+)"|"([A-Za-z]+)"\s*==\s*timeframe\.period')
    for i, raw in enumerate(lines):
        raw_nc = strip_comments_only(raw)
        m = pat.search(raw_nc)
        if m:
            unit = m.group(1) or m.group(2)
            result.add(i + 1, "PINE016",
                        f"timeframe.period compared to \"{unit}\" (no multiplier) — in v6, "
                        f"timeframe.period always includes a multiplier (e.g. \"1{unit}\" not \"{unit}\"), "
                        f"so this comparison may never match.")


def check_lazy_eval_trap(statements, result):
    token_re = re.compile(r'\b(and|or)\b')
    call_re = re.compile(r'\b(ta|request)\.\w+\s*\(')
    for stmt in statements:
        text = stmt["stripped"]
        token_matches = list(token_re.finditer(text))
        if not token_matches:
            continue
        first_token_pos = token_matches[0].start()
        for m in call_re.finditer(text):
            if m.start() > first_token_pos:
                result.add(stmt["start"], "PINE017",
                            f"'{m.group(0).rstrip('(')}(...)' appears after an and/or in this condition — "
                            f"Pine v6 uses lazy (short-circuit) evaluation, so this call may not run on "
                            f"every bar, which can corrupt functions that depend on running every bar "
                            f"(e.g. ta.rsi()). Consider computing it in a variable above the condition.")
                break


NAME_DECL_RE = re.compile(
    r'^\s*(?:var(?:ip)?\s+)?(?:int|float|bool|string|color|label|line|box|table|'
    r'array(?:<[^>]*>)?|matrix(?:<[^>]*>)?|map(?:<[^>]*>)?)?\s*([a-zA-Z_]\w*)\s*=(?![=>])'
)


def check_naming_convention(statements, lines, result):
    """Only checks each logical statement's FIRST physical line — continuation
    lines of a wrapped call (e.g. named args on line 2 of a multi-line
    strategy() call) are never genuine top-level declarations, and checking
    them causes false positives like flagging `default_qty_type=` as a badly
    named variable."""
    seen = set()
    keywords = {"if", "for", "while", "switch", "else"}
    for stmt in statements:
        start_line_text = lines[stmt["start"] - 1]
        line = strip_strings_and_comments(start_line_text)
        m = NAME_DECL_RE.match(line)
        if not m:
            continue
        name = m.group(1)
        if name in seen or name in keywords:
            continue
        seen.add(name)
        is_all_caps_constant = name.upper() == name and any(c.isalpha() for c in name)
        if is_all_caps_constant:
            continue
        if "_" in name:
            result.add(stmt["start"], "PINE018",
                        f"'{name}' looks like snake_case — Pine style guide recommends camelCase for "
                        f"variables (SNAKE_CASE is reserved for constants).")
        elif name[0].isupper():
            result.add(stmt["start"], "PINE018",
                        f"'{name}' looks like PascalCase — Pine style guide recommends camelCase "
                        f"(lowercase first letter) for variables.")


def check_indentation(lines, result):
    uses_tabs = False
    uses_spaces = False
    for i, raw in enumerate(lines):
        ws_match = re.match(r'^[ \t]*', raw)
        ws = ws_match.group(0) if ws_match else ""
        if not ws or not raw.strip():
            continue
        if ' ' in ws and '\t' in ws:
            result.add(i + 1, "PINE019", "Mixed tabs and spaces in this line's indentation.")
        elif '\t' in ws:
            uses_tabs = True
        elif ' ' in ws:
            uses_spaces = True
    if uses_tabs and uses_spaces:
        result.add(0, "PINE026",
                    "This file has some lines indented with tabs and others with spaces — Pine treats "
                    "indentation structurally (like Python); pick one style and use it throughout.")


HEADER_KEYWORD_RE = re.compile(r'\b(if|for|while|else|switch)\b')
ARROW_END_RE = re.compile(r'=>\s*$')


def check_block_headers_have_bodies(lines, statements, result):
    stripped_lines = [strip_strings_and_comments(l) for l in lines]
    # A wrapped statement's continuation lines are indented for readability (the
    # style guide's parenthesised style). The block a `=>` opens is measured from
    # the FIRST line of its logical statement, not from the continuation the
    # arrow happens to land on.
    stmt_start = {}
    for stmt in statements:
        for ln in range(stmt["start"], stmt["end"] + 1):
            stmt_start[ln] = stmt["start"]
    n = len(lines)
    for i in range(n):
        trimmed = stripped_lines[i].strip()
        if not trimmed:
            continue
        is_header = bool(HEADER_KEYWORD_RE.search(trimmed)) or bool(ARROW_END_RE.search(trimmed))
        if not is_header:
            continue
        header_indent = indent_width(lines[stmt_start.get(i + 1, i + 1) - 1])
        j = i + 1
        next_real = None
        while j < n:
            if stripped_lines[j].strip():
                next_real = j
                break
            j += 1
        if next_real is None:
            result.add(i + 1, "PINE020", "Block header with no body following (end of file reached).")
            continue
        if indent_width(lines[next_real]) <= header_indent:
            result.add(i + 1, "PINE020",
                        "Expected an indented statement after this line (if/for/while/else/switch/=> "
                        "always require a following indented block in Pine — there's no same-line body "
                        "syntax).")


def check_int_division_literals(lines, result):
    pat = re.compile(r'(?<![\w.])(\d+)\s*/\s*(\d+)(?!\.\d)(?!\d)')
    for i, raw in enumerate(lines):
        line = strip_strings_and_comments(raw)
        for m in pat.finditer(line):
            a, b = int(m.group(1)), int(m.group(2))
            if b != 0 and a % b != 0:
                result.add(i + 1, "PINE023",
                            f"{a}/{b} divides two integer literals that don't divide evenly — v6 always "
                            f"returns a fraction here ({a / b:.4g}); v5 truncated to {a // b} when both "
                            f"were 'const int'. Wrap with int(...) if truncation is what you want.")


def check_plot_and_drawing_limits(text, lines, result, cfg):
    plot_count = sum(text.count(f) * w for f, w in PLOT_COUNT_WEIGHTS.items())
    max_plots = cfg.get("max_plot_calls", 64)
    warn_ratio = cfg.get("plot_calls_warn_ratio", 0.75)
    if plot_count > max_plots:
        result.add(0, "PINE009",
                    f"~{plot_count} calls to plot-count-consuming functions found (plot/plotarrow/"
                    f"plotbar/plotcandle/plotchar/plotshape/alertcondition/bgcolor/barcolor/fill), "
                    f"already at or over the {max_plots} plot-count limit. Some of these can consume "
                    f"up to 7 plot-counts each depending on how many arguments are dynamic, so the "
                    f"real count may be higher still.")
    elif plot_count > max_plots * warn_ratio:
        result.add(0, "PINE009",
                    f"~{plot_count} calls to plot-count-consuming functions found, approaching the "
                    f"{max_plots} limit. This is a lower-bound estimate — some calls can consume up "
                    f"to 7 plot-counts each.")

    hard_max = cfg.get("max_drawing_hard", 500)
    default_max = cfg.get("max_drawing_default", 50)
    for func, (param, label) in DRAWING_FUNCS.items():
        count = text.count(func)
        if count == 0:
            continue
        if count > hard_max:
            result.add(0, "PINE025",
                        f"{count} {func[:-1]} call(s) found, over the hard cap of {hard_max} {label} IDs.")
        elif count > default_max and param not in text:
            result.add(0, "PINE025",
                        f"{count} {func[:-1]} call(s) found, over the default {default_max}-item "
                        f"display cap — only the most recent {default_max} will show unless {param} "
                        f"is set in the indicator()/strategy() declaration (max {hard_max}).")

    poly_count = text.count("polyline.new(")
    if poly_count > cfg.get("max_polyline", 100):
        result.add(0, "PINE025", f"{poly_count} polyline.new() calls found, over the 100 polyline-ID cap.")

    table_count = text.count("table.new(")
    if table_count > cfg.get("max_tables", 9):
        result.add(0, "PINE025",
                    f"{table_count} table.new() call-sites found in source, over the 9-table-on-chart "
                    f"cap (one per position.* slot). If all are reachable at once only 9 will show — "
                    f"consider reusing one `var table` per position instead.")


# ---------------------------------------------------------------------------
# Symbol table — the closest this linter gets to actually parsing Pine.
#
# It is deliberately permissive about what counts as a DECLARATION and strict
# about what counts as a READ. That asymmetry is the safety margin: over-
# collecting declarations only costs detection power, while under-collecting
# them would invent false "undeclared" findings on correct code.
# ---------------------------------------------------------------------------
IDENT_ASSIGN_RE = re.compile(r'([A-Za-z_]\w*)\s*(:=|=)(?!=)')
TUPLE_DECL_RE = re.compile(r'^\s*\[([^\]]+)\]\s*=(?!=)')
FOR_IN_RE = re.compile(r'^\s*for\s+(?:\[([^\]]+)\]|([A-Za-z_]\w*))\s+in\b')
TYPE_BLOCK_RE = re.compile(r'^\s*type\s+[A-Za-z_]\w*\s*$')
# FUNC_DECL_RE has no capture group; this one names the function.
FUNC_NAME_RE = re.compile(r'^([a-zA-Z_]\w*)\s*\([^)]*\)\s*=>')


def _lines_with_depths(lines):
    """Yields (index, stripped_text, [paren_depth_before_each_char]).

    Depth carries across physical lines, so an argument sitting on its own line
    inside a wrapped call is still seen as depth > 0 — which is what keeps a
    named argument (`title=`) from being mistaken for a declaration."""
    depth = 0
    for i, raw in enumerate(lines):
        text = strip_strings_and_comments(raw)
        depths = []
        for ch in text:
            depths.append(depth)
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth = max(0, depth - 1)
        yield i, text, depths


def collect_symbols(lines):
    """Returns (symbols, writes).

    symbols maps a declared name to {"line", "reads", "kind"}; writes is every
    (line_no, name) reassigned with := or +=. Only assignments at paren depth 0
    are declarations. Function parameters and loop variables are collected too,
    because a := to one of those is legal and must not be called undeclared."""
    symbols = {}
    writes = []
    assign_positions = set()
    in_type_block = False

    def declare(name, idx, kind):
        if name and re.fullmatch(r'[A-Za-z_]\w*', name) and name not in symbols:
            symbols[name] = {"line": idx + 1, "reads": 0, "kind": kind}

    for i, text, depths in _lines_with_depths(lines):
        if not text.strip():
            continue
        # A `type` block's fields are members, not variables — they are only
        # ever touched as obj.field, so collecting them would be noise.
        if TYPE_BLOCK_RE.match(text):
            in_type_block = True
            continue
        if in_type_block:
            if indent_width(lines[i]) > 0:
                continue
            in_type_block = False

        m_tuple = TUPLE_DECL_RE.match(text)
        if m_tuple:
            for part in m_tuple.group(1).split(","):
                declare(part.strip().split()[-1] if part.strip() else "", i, "var")
            continue

        m_for = FOR_IN_RE.match(text)
        if m_for:
            group = m_for.group(1) or m_for.group(2) or ""
            for part in group.split(","):
                declare(part.strip(), i, "loop")
            continue

        m_func = FUNC_NAME_RE.match(text.strip())
        if m_func and indent_width(lines[i]) == 0:
            declare(m_func.group(1), i, "func")
            params = call_arg_text(text, m_func.group(1) + "(")
            for part in split_top_level_args(params or ""):
                bare = part.split("=")[0].strip().split()
                if bare:
                    declare(bare[-1], i, "param")
            continue

        is_for = text.lstrip().startswith("for ")
        for m in IDENT_ASSIGN_RE.finditer(text):
            if depths[m.start()] != 0:
                continue
            if m.start() > 0 and text[m.start() - 1] == '.':
                continue
            name, op = m.group(1), m.group(2)
            assign_positions.add((i, m.start()))
            if op == "=":
                declare(name, i, "loop" if is_for else "var")
            else:
                writes.append((i + 1, name))

    # Reads. Anything that is not an assignment target and not a member access
    # counts, which is why a write-only variable still reports zero.
    for i, text, _depths in _lines_with_depths(lines):
        for m in re.finditer(r'[A-Za-z_]\w*', text):
            name = m.group(0)
            if name not in symbols:
                continue
            if (i, m.start()) in assign_positions:
                continue
            if m.start() > 0 and text[m.start() - 1] == '.':
                continue
            if symbols[name]["line"] == i + 1 and symbols[name]["kind"] in ("var", "loop"):
                continue          # a declaration is not a read of its own name
            symbols[name]["reads"] += 1
    return symbols, writes


def check_undeclared_assignment(lines, result):
    """PINE050 — `x := 1` where x was never declared is "Undeclared identifier"
    on TradingView. It is the most common typo class in Pine, and one a purely
    regex-based linter could not see before this file had a symbol table."""
    symbols, writes = collect_symbols(lines)
    reported = set()
    for line_no, name in writes:
        if name in symbols or name in reported:
            continue
        reported.add(name)
        result.add(line_no, "PINE050",
                   "'%s' is reassigned with := but never declared anywhere in the file. "
                   "Pine rejects that as an undeclared identifier — declare it first "
                   "(`%s = ...`, or `var %s = ...` to persist across bars). If this is a "
                   "typo, the declared name is the one to use." % (name, name, name))


def check_unused_variable(lines, result):
    """PINE051 — declared and never read. Two different defects share this
    shape: a leftover from a deleted feature, and a variable that is only ever
    written to. This repo has shipped both."""
    symbols, _writes = collect_symbols(lines)
    for name, info in sorted(symbols.items(), key=lambda kv: kv[1]["line"]):
        if info["kind"] != "var" or info["reads"] > 0 or name.startswith("_"):
            continue
        result.add(info["line"], "PINE051",
                   "'%s' is declared here and never read afterwards. Either it is left "
                   "over from code that was removed, or the value is write-only — in "
                   "which case the call producing it can stand on its own line without "
                   "the assignment." % name)


def _loop_bodies(lines):
    """Yields (index, indent, header_text, [(index, text)]) for each for/while
    header and the block indented under it."""
    stripped = [strip_strings_and_comments(l) for l in lines]
    out = []
    for i, text in enumerate(stripped):
        head = text.strip()
        if not (head.startswith("for ") or head.startswith("while ")):
            continue
        indent = indent_width(lines[i])
        body = []
        j = i + 1
        while j < len(lines):
            if not stripped[j].strip():
                j += 1
                continue
            if indent_width(lines[j]) <= indent:
                break
            body.append((j, stripped[j]))
            j += 1
        out.append((i, indent, text, body))
    return out


def check_drawing_in_loop_budget(lines, statements, result):
    """PINE052 — PINE025 counts call SITES, which is the wrong unit once the
    drawings are created in a loop: one box.new() inside a pool loop can
    allocate hundreds. Without max_boxes_count the declaration defaults to 50,
    and TradingView drops the older ones with no error at all."""
    decl = find_declaration_statement(statements)
    decl_text = decl["stripped"] if decl else ""
    seen = set()
    for _i, _indent, _head, body in _loop_bodies(lines):
        for idx, text in body:
            for func, (param, label) in DRAWING_FUNCS.items():
                if func not in text or param in decl_text or func in seen:
                    continue
                seen.add(func)
                result.add(idx + 1, "PINE052",
                           "%s is called inside a loop, so the script can create far more "
                           "%ss than its call sites suggest, but the declaration does not "
                           "set %s. The default is 50 and TradingView silently keeps only "
                           "the newest — no error, just a chart missing its older "
                           "drawings. Set %s (max 500)."
                           % (func[:-1], label, param, param))


def _resolve_input_maxvals(statements):
    """Maps a variable name to the maxval of the input.int() assigned to it, so
    a loop bound written as an input can be costed at its worst case."""
    bounds = {}
    for stmt in statements:
        text = strip_comments_only_multi(stmt["raw_nc"])
        m = re.search(r'([A-Za-z_]\w*)\s*=\s*input\s*\.\s*int\s*\(', text)
        if not m:
            continue
        args = split_top_level_args(call_arg_text(text, "input.int(") or "")
        maxval = named_arg(args, "maxval")
        if maxval and re.fullmatch(r'\d+', maxval.strip()):
            bounds[m.group(1)] = int(maxval)
    return bounds


def _loop_worst_case(header, bounds):
    """Worst-case iteration count for ONE loop header, or None when the bound
    cannot be resolved. Unknown stays silent — a guess here would be a lie."""
    m = re.search(r'\bfor\s+[A-Za-z_]\w*\s*=\s*(\S+)\s+to\s+([A-Za-z_]\w*|\d+)', header)
    if not m:
        return None
    start_txt, end_txt = m.group(1), m.group(2)
    if not re.fullmatch(r'\d+', start_txt):
        return None
    if re.fullmatch(r'\d+', end_txt):
        end = int(end_txt)
    elif end_txt in bounds:
        end = bounds[end_txt]
    else:
        return None
    return max(0, end - int(start_txt) + 1)


def _nest_cost(loop, loops, bounds):
    """Worst case for a loop INCLUDING its nested loops. Sibling loops are
    additive, not multiplicative, so only the heaviest child multiplies —
    overstating that would produce warnings nobody should act on."""
    i, indent, header, body = loop
    own = _loop_worst_case(header, bounds)
    if own is None:
        return None, []
    body_idx = {idx for idx, _txt in body}
    children = [l for l in loops if l[0] in body_idx]
    direct = [c for c in children
              if not any(c[0] in {idx for idx, _t in o[3]} for o in children if o is not c)]
    best, best_chain = 1, []
    for child in direct:
        cost, chain = _nest_cost(child, loops, bounds)
        if cost is None:
            return None, []
        if cost > best:
            best, best_chain = cost, chain
    return own * best, [own] + best_chain


def check_loop_cost(lines, statements, result, cfg):
    """PINE053 — Pine aborts a loop running longer than 500ms and a script
    running longer than 20s. Both limits are reached by multiplication: an outer
    bound and an inner bound that are each perfectly reasonable alone."""
    budget = cfg.get("max_loop_iterations", 100000)
    bounds = _resolve_input_maxvals(statements)
    loops = _loop_bodies(lines)
    nested = set()
    for _i, _ind, _h, body in loops:
        nested |= {idx for idx, _t in body}
    for loop in loops:
        if loop[0] in nested:
            continue          # only report the outermost loop of a nest
        worst, chain = _nest_cost(loop, loops, bounds)
        if worst is None or worst <= budget:
            continue
        result.add(loop[0] + 1, "PINE053",
                   "This loop nest can run %s = %s iterations in the worst case, over "
                   "the %s budget. Pine aborts a loop that exceeds 500ms and a script "
                   "that exceeds 20s, and the worst case is what a user reaches by "
                   "turning an input up — not a hypothetical. Lower a maxval, or hoist "
                   "work out of the inner loop."
                   % (" x ".join(str(c) for c in chain), format(worst, ","), format(budget, ",")))


# ---------------------------------------------------------------------------
# --fix — mechanical repairs
#
# A rule qualifies only when there is exactly ONE correct rewrite. Anything
# needing intent (which title? which overlay setting? how to split a long line?)
# stays a finding, because a linter that guesses is worse than one that nags.
# ---------------------------------------------------------------------------
def _replace_outside_strings(line, pattern, repl):
    """Applies a regex to the code part of a line only, leaving string literals
    and the trailing comment untouched. Returns (new_line, n_changes)."""
    out = []
    changes = 0
    in_str = None
    i = 0
    buf = []

    def flush():
        nonlocal changes
        if not buf:
            return ""
        text = "".join(buf)
        new, n = pattern.subn(repl, text)
        changes += n
        buf.clear()
        return new

    while i < len(line):
        ch = line[i]
        if in_str:
            out.append(ch)
            if ch == '\\' and i + 1 < len(line):
                out.append(line[i + 1])
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in ('"', "'"):
            out.append(flush())
            in_str = ch
            out.append(ch)
            i += 1
            continue
        if ch == '/' and i + 1 < len(line) and line[i + 1] == '/':
            out.append(flush())
            out.append(line[i:])
            return "".join(out), changes
        buf.append(ch)
        i += 1
    out.append(flush())
    return "".join(out), changes


STUDY_RE = re.compile(r'(?<![.\w])study\s*\(')
BARE_SECURITY_RE = re.compile(r'(?<![.\w])security\s*\(')
LINEWIDTH_ZERO_RE = re.compile(r'\blinewidth\s*=\s*(?:0|-\d+)\b')
OVERSIZED_RE = re.compile(r'\bsize\.(large|huge)\b')


INT_DIV_LITERAL_RE = re.compile(r'(?<![.\w])(\d+)\s*/\s*(\d+)(?![.\d])')


def apply_fixes(lines):
    """Returns (new_lines, [(line_no, code, description)]).

    Line-based on purpose: every fix here is a substitution inside one line, so
    line numbers never shift and a fixed file can be re-linted meaningfully."""
    fixed = []
    log = []
    for i, raw in enumerate(lines):
        line = raw
        line, n = _replace_outside_strings(line, STUDY_RE, "indicator(")
        if n:
            log.append((i + 1, "PINE004", "study() -> indicator()"))
        line, n = _replace_outside_strings(line, BARE_SECURITY_RE, "request.security(")
        if n:
            log.append((i + 1, "PINE004", "security() -> request.security()"))
        line, n = _replace_outside_strings(line, LINEWIDTH_ZERO_RE, "linewidth=1")
        if n:
            log.append((i + 1, "PINE012", "linewidth below the v6 minimum -> linewidth=1"))
        line, n = _replace_outside_strings(line, OVERSIZED_RE, "size.normal")
        if n:
            log.append((i + 1, "PINE041", "size.large/size.huge -> size.normal"))
        # `2 / 3` between int literals reads as integer division to anyone who
        # learned Pine on v5. Spelling one side as a float states the intent and
        # changes nothing about what v6 already does.
        line, n = _replace_outside_strings(line, INT_DIV_LITERAL_RE, r"\g<1>.0 / \g<2>")
        if n:
            log.append((i + 1, "PINE023", "int/int literal division -> explicit float"))
        # Leading tabs last, so the column maths above is done on the original.
        stripped_lead = len(line) - len(line.lstrip("\t"))
        if stripped_lead:
            line = "    " * stripped_lead + line[stripped_lead:]
            log.append((i + 1, "PINE019", "leading tab indentation -> 4 spaces"))
        fixed.append(line)
    return fixed, log


def run_fix(path, dry_run):
    """Applies every mechanical fix to `path`. Prints what changed and returns
    an exit code. With dry_run nothing is written."""
    original = Path(path).read_text(encoding="utf-8")
    lines = original.splitlines()
    fixed, log = apply_fixes(lines)
    if not log:
        print(f"{path}: nothing to fix ({len(FIXABLE)} rules are mechanically fixable: "
              f"{', '.join(sorted(FIXABLE))}).")
        return 0
    for line_no, code, what in log:
        print(f"{path}:{line_no}: [{code}] {what}")
    print()
    if dry_run:
        print(f"{len(log)} fix(es) available. Re-run without --dry-run to apply them.")
        return 0
    ending = "\r\n" if "\r\n" in original else "\n"
    trailing = ending if original.endswith(("\n", "\r")) else ""
    Path(path).write_text(ending.join(fixed) + trailing, encoding="utf-8")
    print(f"Applied {len(log)} fix(es) to {path}.")
    return 0


# @rule PINE054
VAR_COLLECTION_RE = re.compile(
    r'^\s*var(?:ip)?\s+(?:array|matrix|map)\s*<[^>]*>\s*([A-Za-z_]\w*)\s*=')
GROW_CALL_RE = re.compile(
    r'(?:array|matrix|map)\s*\.\s*(push|unshift|insert|put)\s*\(\s*([A-Za-z_]\w*)')
# Growing a DRAWING pool is the one legitimate unguarded case: the pool loop is
# bounded by array.size(), so it converges instead of accumulating.
DRAWING_CTOR_RE = re.compile(r'\b(?:box|line|label|polyline|table|linefill)\s*\.\s*new\s*\(')
CONFIRM_GUARD_RE = re.compile(
    r'barstate\s*\.\s*(isconfirmed|isnew|ishistory|isfirst)|not\s+barstate\s*\.\s*isrealtime')


def check_var_collection_realtime_growth(lines, result):
    """PINE054 — `var` restores the variable on a realtime rollback, not the
    contents of the array it points to. A push that happened on one tick stays
    pushed even when the condition that caused it is false on the next.

    This bit twice in this repo: a pivot that appears mid-bar and vanishes
    before the close still left its swing recorded, and an order block whose
    break condition un-broke still left the block. There is no error message —
    the chart just accumulates things that never really happened."""
    collections = set()
    for raw in lines:
        m = VAR_COLLECTION_RE.match(strip_strings_and_comments(raw))
        if m:
            collections.add(m.group(1))
    if not collections:
        return
    # A collection that is cleared somewhere is a reused scratch buffer, not
    # accumulated state: it is emptied before each refill, so a push from a tick
    # that turns out not to count is overwritten rather than kept.
    # performance-guide.md recommends exactly this instead of allocating a fresh
    # array per bar, and a rule that fires on the idiom its own docs teach is a
    # rule that gets suppressed.
    joined = "\n".join(strip_strings_and_comments(l) for l in lines)
    collections = {c for c in collections
                   if not re.search(r'(?:array|matrix|map)\s*\.\s*clear\s*\(\s*'
                                    + re.escape(c) + r'\s*\)', joined)}
    if not collections:
        return

    stripped = [strip_strings_and_comments(l) for l in lines]
    reported = set()
    for i, text in enumerate(stripped):
        m = GROW_CALL_RE.search(text)
        if not m or m.group(2) not in collections or m.group(2) in reported:
            continue
        if DRAWING_CTOR_RE.search(text):
            continue          # a pool grow, bounded by its own size check
        indent = indent_width(lines[i])
        if indent == 0:
            continue          # unconditional at global scope: runs every bar anyway
        # Walk out through the enclosing blocks looking for a guard.
        guarded = False
        inside_pool_loop = False
        depth = indent
        for j in range(i - 1, -1, -1):
            if not stripped[j].strip():
                continue
            j_indent = indent_width(lines[j])
            if j_indent >= depth:
                continue
            depth = j_indent
            head = stripped[j].strip()
            if CONFIRM_GUARD_RE.search(head):
                guarded = True
                break
            if head.startswith("while ") and "array.size" in head:
                inside_pool_loop = True
                break
            if head.startswith("if ") or head.startswith("for ") or head.startswith("while "):
                continue
            break             # a function body or an unindented statement
        if guarded or inside_pool_loop:
            continue
        reported.add(m.group(2))
        result.add(i + 1, "PINE054",
                   "'%s' is a var collection grown inside a conditional block with no "
                   "barstate.isconfirmed guard. On a realtime bar `var` restores the "
                   "VARIABLE on each tick, never the contents of the array it points "
                   "at — so this %s() is permanent even if the condition that caused "
                   "it is false on the next tick. Conditions built on ta.pivothigh, a "
                   "break of a level, or anything else reading the forming bar do "
                   "exactly that. Guard the mutation with barstate.isconfirmed."
                   % (m.group(2), m.group(1)))


# @rule PINE055
def _global_declaration_lines(lines):
    """Maps every name declared at COLUMN 0 to the line it was declared on.

    Column 0 is the whole test: a name indented under something is a local, and
    locals are not what this rule is about."""
    declared = {}
    in_type_block = False
    for i, text, depths in _lines_with_depths(lines):
        if not text.strip():
            continue
        if TYPE_BLOCK_RE.match(text):
            in_type_block = True
            declared.setdefault(text.strip().split()[1], i + 1)
            continue
        if in_type_block:
            if indent_width(lines[i]) > 0:
                continue
            in_type_block = False
        if indent_width(lines[i]) != 0:
            continue
        m_func = FUNC_NAME_RE.match(text.strip())
        if m_func:
            declared.setdefault(m_func.group(1), i + 1)
            continue
        m_tuple = TUPLE_DECL_RE.match(text)
        if m_tuple:
            for part in m_tuple.group(1).split(","):
                name = part.strip().split()[-1] if part.strip() else ""
                if name:
                    declared.setdefault(name, i + 1)
            continue
        for m in IDENT_ASSIGN_RE.finditer(text):
            if depths[m.start()] != 0 or m.group(2) != "=":
                continue
            if m.start() > 0 and text[m.start() - 1] == '.':
                continue
            declared.setdefault(m.group(1), i + 1)
    return declared


def check_forward_global_reference(lines, result):
    """PINE055 — Pine resolves identifiers in textual order, so a function body
    can only see what was declared ABOVE its own declaration. Referencing a
    global declared later is `Undeclared identifier`, and the error points at
    the function rather than at the declaration that is in the wrong place.

    This is easy to create by accident: adding a `request.*` call in the
    calculations section and then reading it from a helper that happens to be
    declared earlier looks perfectly reasonable in a diff."""
    declared = _global_declaration_lines(lines)
    if not declared:
        return
    reported = set()
    for decl_idx, body in iter_function_bodies(lines):
        decl_line = decl_idx + 1
        # Names the function introduces itself are not forward references.
        local = set()
        header = strip_strings_and_comments(lines[decl_idx]).strip()
        m_func = FUNC_NAME_RE.match(header)
        if m_func:
            params = call_arg_text(header, m_func.group(1) + "(")
            for part in split_top_level_args(params or ""):
                bare = part.split("=")[0].strip().split()
                if bare:
                    local.add(bare[-1])
        for _idx, text in body:
            for m in IDENT_ASSIGN_RE.finditer(text):
                local.add(m.group(1))
            m_for = FOR_IN_RE.match(text)
            if m_for:
                group = m_for.group(1) or m_for.group(2) or ""
                for part in group.split(","):
                    local.add(part.strip())
        for idx, text in body:
            for m in re.finditer(r'[A-Za-z_]\w*', text):
                name = m.group(0)
                if name in local or name not in declared:
                    continue
                if m.start() > 0 and text[m.start() - 1] == '.':
                    continue
                if declared[name] <= decl_line:
                    continue
                key = (m_func.group(1) if m_func else decl_line, name)
                if key in reported:
                    continue
                reported.add(key)
                result.add(idx + 1, "PINE055",
                           "'%s' is declared on line %d, BELOW this function. Pine "
                           "resolves identifiers in textual order, so a function body "
                           "can only see what was declared above its own declaration — "
                           "this is `Undeclared identifier` at compile time, and the "
                           "error points here rather than at the declaration that is in "
                           "the wrong place. Move the declaration above the function."
                           % (name, declared[name]))


# @rule PINE056
def check_unused_function(lines, result):
    """PINE056 — a function declared at global scope and never called.

    Pine has no dead-code elimination worth relying on and no warning of its
    own, so an orphaned helper survives every refactor that was supposed to
    remove it. `export`ed library functions are exempt: being uncalled inside
    the library is the normal case for them."""
    declared = {}
    for i, raw in enumerate(lines):
        text = strip_strings_and_comments(raw)
        if indent_width(raw) != 0 or text.lstrip().startswith("export "):
            continue
        m = FUNC_NAME_RE.match(text.strip())
        if m:
            declared.setdefault(m.group(1), i + 1)
    if not declared:
        return
    uses = {name: 0 for name in declared}
    for i, raw in enumerate(lines):
        text = strip_strings_and_comments(raw)
        for m in re.finditer(r'[A-Za-z_]\w*', text):
            name = m.group(0)
            if name not in uses:
                continue
            if declared[name] == i + 1 and m.start() == len(text) - len(text.lstrip()):
                continue          # the declaration itself
            if m.start() > 0 and text[m.start() - 1] == '.':
                continue
            uses[name] += 1
    for name, line_no in sorted(declared.items(), key=lambda kv: kv[1]):
        if uses[name] == 0:
            result.add(line_no, "PINE056",
                       "'%s()' is declared here and never called. Pine gives no warning "
                       "of its own for this, so an orphaned helper survives every "
                       "refactor that meant to remove it — and keeps being maintained, "
                       "read and kept compiling for nothing." % name)


# @rule PINE057
CONST_COMPARE_RE = re.compile(
    r'\b(?:if|while)\s+(-?\d+(?:\.\d+)?)\s*(==|!=|<=|>=|<|>)\s*(-?\d+(?:\.\d+)?)\s*$')
CONST_LITERAL_RE = re.compile(r'\b(?:if|while)\s+(true|false)\s*$')
SELF_COMPARE_RE = re.compile(r'\b(?:if|while)\s+([A-Za-z_]\w*)\s*(==|!=)\s*\1\s*$')


def _const_verdict(lhs, op, rhs):
    a, b = float(lhs), float(rhs)
    return {"==": a == b, "!=": a != b, "<": a < b,
            ">": a > b, "<=": a <= b, ">=": a >= b}[op]


def check_constant_condition(lines, result):
    """PINE057 — a condition whose value cannot change.

    `if true` is usually a debug switch someone forgot, `if 2 > 1` is usually a
    half-finished edit, and `x == x` is usually a typo for a different variable.
    All three compile, none is ever reported, and each silently disables or
    permanently enables the block under it."""
    for i, raw in enumerate(lines):
        text = strip_strings_and_comments(raw).rstrip()
        if not text.strip():
            continue
        m = CONST_COMPARE_RE.search(text)
        if m:
            verdict = _const_verdict(m.group(1), m.group(2), m.group(3))
            result.add(i + 1, "PINE057",
                       "`%s %s %s` is always %s — both sides are literals, so this "
                       "condition can never change. The block under it is either dead "
                       "code or permanently on."
                       % (m.group(1), m.group(2), m.group(3), str(verdict).lower()))
            continue
        m = CONST_LITERAL_RE.search(text)
        if m:
            result.add(i + 1, "PINE057",
                       "Condition is the literal `%s`. Usually a debug switch left "
                       "behind: the block under it is permanently %s."
                       % (m.group(1), "on" if m.group(1) == "true" else "dead"))
            continue
        m = SELF_COMPARE_RE.search(text)
        if m:
            result.add(i + 1, "PINE057",
                       "`%s` is compared with itself, which is always %s. This is "
                       "almost always a typo for a different variable — and note that "
                       "it does NOT work as an na check either; use na(%s)."
                       % (m.group(1), "true" if m.group(2) == "==" else "false",
                          m.group(1)))


# @rule PINE058
BUILTIN_NAMESPACES = frozenset({
    "math", "ta", "array", "matrix", "map", "str", "color", "label", "line",
    "box", "table", "polyline", "linefill", "request", "syminfo", "timeframe",
    "barstate", "strategy", "input", "format", "display", "position", "size",
    "location", "shape", "extend", "order", "alert", "session", "xloc", "yloc",
    "chart", "runtime", "currency", "dayofweek", "text", "font", "scale",
    "barmerge", "adjustment", "plot", "hline", "earnings", "dividends",
    "splits", "math_pi",
})


def check_namespace_shadowing(lines, result):
    """PINE058 — a name shadows a built-in namespace AND is dereferenced.

    Both halves are required. A parameter called `label` is harmless until
    something in that scope writes `label.new(...)`, at which point the shadow
    wins and the call reads the parameter. Flagging the name alone would fire
    on every `string label` in the repo and get the rule switched off; flagging
    the dereference alone would miss where the shadow came from.

    This shipped here: `entryAlertPayload(..., string format)` used
    `format.mintick` in its body, so the price was formatted with the string
    "Text" instead of the tick format. Nothing errored — passing a string to a
    function that accepts one is legal — so it showed up as wrong text in an
    alert. Found by RUNNING the script, not by reading it.
    """
    reported = set()

    def flag(line_no, name, where):
        if (line_no, name) in reported:
            return
        reported.add((line_no, name))
        result.add(line_no, "PINE058",
                   "'%s' shadows the built-in namespace of the same name, and %s "
                   "dereferences it as '%s.something'. The shadow wins, so that "
                   "reads THIS value instead of the built-in — and nothing errors, "
                   "because passing the wrong thing to a function that accepts it "
                   "is legal. Rename it." % (name, where, name))

    # 1. Function parameters, checked against their own body.
    for decl_idx, body in iter_function_bodies(lines):
        head = strip_strings_and_comments(lines[decl_idx]).strip()
        m = FUNC_NAME_RE.match(head)
        if not m:
            continue
        params = call_arg_text(head, m.group(1) + "(")
        body_text = " ".join(text for _idx, text in body)
        for part in split_top_level_args(params or ""):
            bare = part.split("=")[0].strip().split()
            if not bare:
                continue
            name = bare[-1]
            if name in BUILTIN_NAMESPACES and re.search(
                    r'(?<![.\w])' + re.escape(name) + r'\s*\.', body_text):
                flag(decl_idx + 1, name, "its body")

    # 2. Declarations at global scope, checked against the whole file.
    joined = " ".join(strip_strings_and_comments(l) for l in lines)
    for i, text, depths in _lines_with_depths(lines):
        if not text.strip() or indent_width(lines[i]) != 0:
            continue
        for m in IDENT_ASSIGN_RE.finditer(text):
            if depths[m.start()] != 0 or m.group(2) != "=":
                continue
            if m.start() > 0 and text[m.start() - 1] == '.':
                continue
            name = m.group(1)
            if name in BUILTIN_NAMESPACES and re.search(
                    r'(?<![.\w])' + re.escape(name) + r'\s*\.', joined):
                flag(i + 1, name, "the file")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def load_config(config_path):
    cfg = dict(DEFAULT_CONFIG)
    if config_path and Path(config_path).exists():
        try:
            with open(config_path) as f:
                user_cfg = json.load(f)
            cfg.update(user_cfg)
        except (json.JSONDecodeError, OSError) as e:
            print(f"warning: could not read config {config_path}: {e}", file=sys.stderr)
    return cfg


def lint_file(path, cfg):
    result = LintResult()
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        result.add(0, "PINE003", f"Could not read file: {e}")
        return result
    lines = text.splitlines()
    statements = build_logical_statements(lines)

    check_version_pragma(lines, result)
    check_declaration(text, statements, result)
    check_has_output(text, result)
    check_balanced_delimiters(lines, result)
    check_deprecated_syntax(lines, result)
    check_security_lookahead(statements, result, cfg)
    check_var_accumulator(lines, result)
    check_line_length(lines, result, cfg)
    check_inputs_have_titles(statements, result)
    check_when_removed(statements, result)
    check_exit_has_level(statements, result)
    check_exit_level_pairs(statements, result)
    check_exit_tick_params(statements, result)
    check_position_avg_price_guard(text, result)
    check_order_qty_range(statements, result)
    check_exit_from_entry(statements, result)
    check_entries_have_exits(text, result)
    check_table_cell_text_color(statements, result)
    check_array_alloc_in_block(lines, result)
    check_drawing_churn(lines, result)
    check_duplicate_security(statements, result)
    check_plot_has_title(statements, result)
    check_oversized_text(lines, result)
    check_global_mutation_in_function(lines, result)
    check_function_branch_types(lines, result)
    check_seconds_timeframe(lines, result)
    check_na_comparison(lines, result)
    check_input_scope(lines, statements, result)
    check_plot_scope(lines, statements, result)
    check_strategy_call_scope(lines, result)
    check_request_count(statements, result, cfg)
    check_transp_removed(statements, result)
    check_linewidth_minimum(statements, result)
    check_switch_default(lines, result)
    check_history_on_literal(lines, result)
    check_duplicate_named_params(statements, result)
    check_timeframe_period_compare(lines, result)
    check_lazy_eval_trap(statements, result)
    check_naming_convention(statements, lines, result)
    check_indentation(lines, result)
    check_block_headers_have_bodies(lines, statements, result)
    check_int_division_literals(lines, result)
    check_plot_and_drawing_limits(text, lines, result, cfg)
    check_undeclared_assignment(lines, result)
    check_unused_variable(lines, result)
    check_drawing_in_loop_budget(lines, statements, result)
    check_loop_cost(lines, statements, result, cfg)
    check_var_collection_realtime_growth(lines, result)
    check_forward_global_reference(lines, result)
    check_unused_function(lines, result)
    check_constant_condition(lines, result)
    check_namespace_shadowing(lines, result)

    file_wide, next_line, same_line = parse_suppressions(lines)
    filtered = []
    for f in result.findings:
        if f.code in file_wide:
            continue
        if f.code in next_line.get(f.line, set()):
            continue
        if f.code in same_line.get(f.line, set()):
            continue
        filtered.append(f)
    result.findings = filtered
    return result


def print_human(args, result):
    for f in sorted(result.findings, key=lambda x: (x.line, x.code)):
        print(f"{args.file}:{f.line}: {f.severity.upper()} [{f.code}]: {f.msg}")
    print()
    n_err = len(result.by_severity("error"))
    n_warn = len(result.by_severity("warning"))
    n_info = len(result.by_severity("info"))
    print(f"{n_err} error(s), {n_warn} warning(s), {n_info} note(s).")


def print_editor(args, result):
    """`path:line:col: severity: message (CODE)` — the shape every editor's
    problem matcher already understands. Column is always 1: these rules match
    lines, not spans, and inventing a column would put the squiggle somewhere
    the finding is not."""
    for f in sorted(result.findings, key=lambda x: (x.line, x.code)):
        print(f"{args.file}:{max(f.line, 1)}:1: {f.severity}: {f.msg} ({f.code})")


def print_github(args, result):
    """GitHub Actions annotations, so CI findings land on the diff itself
    instead of inside a log nobody opens."""
    level = {"error": "error", "warning": "warning", "info": "notice"}
    for f in sorted(result.findings, key=lambda x: (x.line, x.code)):
        # An annotation is one line: a raw newline truncates it at the break,
        # and a bare % is read as the start of an escape sequence.
        msg = " ".join(f.msg.split()).replace("%", "%25")
        print(f"::{level[f.severity]} file={args.file},line={max(f.line, 1)},"
              f"title={f.code}::{msg}")


def print_json(args, result):
    payload = {
        "file": args.file,
        "findings": [
            {"line": f.line, "code": f.code, "severity": f.severity, "message": f.msg}
            for f in sorted(result.findings, key=lambda x: (x.line, x.code))
        ],
        "summary": {
            "errors": len(result.by_severity("error")),
            "warnings": len(result.by_severity("warning")),
            "notes": len(result.by_severity("info")),
        },
    }
    print(json.dumps(payload, indent=2))


RULES_DOC = Path(__file__).resolve().parent.parent / "references" / "lint-rules.md"


def explain_rule(code):
    """Prints the rule's section from references/lint-rules.md, so you never have
    to go hunting through the catalog after seeing a code in the output."""
    code = code.upper()
    if not code.startswith("PINE"):
        code = "PINE" + code.zfill(3)
    if code not in RULES:
        print(f"error: unknown rule {code}. Run --list-rules to see the catalog.",
              file=sys.stderr)
        return 1
    sev, summary = RULES[code]
    fixable = "  (--fix can repair this automatically)" if code in FIXABLE else ""
    print(f"{code}  [{sev}]  {summary}{fixable}\n")
    if not RULES_DOC.exists():
        print(f"(no catalog found at {RULES_DOC})")
        return 0
    lines = RULES_DOC.read_text(encoding="utf-8").splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith(f"### {code} "):
            start = i
            break
    if start is None:
        print("(this rule has no section in references/lint-rules.md yet)")
        return 0
    for line in lines[start + 1:]:
        if line.startswith("### ") or line.startswith("## "):
            break
        print(line)
    return 0


def parse_baseline(path):
    """Reads a baseline file of `relative/path:CODE` lines. Anything listed is
    treated as pre-existing and not reported, which is how an inherited script
    can adopt the linter without fixing everything in one go."""
    accepted = set()
    if not path or not Path(path).exists():
        return accepted
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" in line:
            _, code = line.rsplit(":", 1)
            accepted.add(code.strip())
    return accepted


def write_baseline(path, file_name, result):
    lines = [
        "# pine_lint baseline — findings recorded as pre-existing and suppressed.",
        "# Delete a line once you have fixed it; the linter will start reporting it again.",
        "",
    ]
    for f in sorted(result.findings, key=lambda x: (x.line, x.code)):
        lines.append(f"{file_name}:{f.code}    # line {f.line}: {f.msg[:70]}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def apply_profile(result, profile):
    """Drops findings below the profile's floor. Filtering, never adding — a
    profile that could introduce a finding would mean `dev` and `publish`
    disagreed about what is true, rather than about what is worth showing."""
    floor = SEVERITY_ORDER[profile["min_severity"]]
    result.findings = [f for f in result.findings
                       if SEVERITY_ORDER[f.severity] >= floor]


def run_watch(args, cfg, profile, strict):
    """Re-lints on every change to the file until interrupted.

    Polls mtime rather than using a filesystem-watch library, because this repo
    has no third-party dependencies and is not going to acquire one for this."""
    import time
    print(f"watching {args.file} — Ctrl+C to stop\n")
    last = None
    try:
        while True:
            try:
                stamp = Path(args.file).stat().st_mtime
            except OSError:
                time.sleep(0.5)
                continue
            if stamp != last:
                last = stamp
                result = lint_file(args.file, cfg)
                apply_profile(result, profile)
                print("\033[2J\033[H", end="")      # clear, so only the current state shows
                print(f"{args.file}  ({time.strftime('%H:%M:%S')})\n")
                print_human(args, result)
                print("\nOK" if result.ok(strict=strict) else "\nFAILING")
            time.sleep(0.4)
    except KeyboardInterrupt:
        print("\nstopped")
        return 0


def make_output_encoding_safe():
    """The rule messages and the docs use en-dashes, arrows and box glyphs. On a
    Windows console (cp1252) printing those raises UnicodeEncodeError and takes
    the whole run down — a linter must never crash on its own output."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass          # already fine, or not a reconfigurable stream


def main():
    """Returns an exit code, or None when it exits via sys.exit()."""
    make_output_encoding_safe()
    parser = argparse.ArgumentParser(description="Rule-based offline linter for Pine Script.")
    parser.add_argument("file", nargs="?", help="Path to a .pine file")
    parser.add_argument("--config", default=None, help="Path to a .pine-lint.json config override")
    parser.add_argument("--json", action="store_true", help="Emit findings as JSON")
    parser.add_argument("--format", choices=("human", "json", "editor", "github"),
                        default=None,
                        help="human (default), json, editor (path:line:col: ...), "
                             "or github (Actions annotations on the diff)")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures (exit 1)")
    parser.add_argument("--profile", choices=sorted(PROFILES),
                        help="dev = errors only, non-fatal. publish = everything, "
                             "warnings fatal. all = everything, nothing fatal (default).")
    parser.add_argument("--watch", action="store_true",
                        help="Re-lint whenever the file changes, until interrupted")
    parser.add_argument("--list-rules", action="store_true", help="Print the full rule catalog and exit")
    parser.add_argument("--explain", metavar="CODE",
                        help="Print the full documentation for one rule and exit")
    parser.add_argument("--baseline", metavar="FILE",
                        help="Suppress the rule codes recorded in FILE")
    parser.add_argument("--write-baseline", metavar="FILE",
                        help="Record the current findings to FILE and exit 0")
    parser.add_argument("--fix", action="store_true",
                        help="Apply the mechanical fixes (" + ", ".join(sorted(FIXABLE)) + ")")
    parser.add_argument("--dry-run", action="store_true",
                        help="With --fix: show what would change without writing")
    args = parser.parse_args()

    if args.list_rules:
        for code in sorted(RULES):
            sev, summary = RULES[code]
            mark = "  [--fix]" if code in FIXABLE else ""
            print(f"{code}\t{sev:8s}\t{summary}{mark}")
        sys.exit(0)

    if args.explain:
        sys.exit(explain_rule(args.explain))

    if not args.file:
        parser.error("the following arguments are required: file "
                     "(unless --list-rules or --explain)")

    if not Path(args.file).exists():
        print(f"error: file not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    if args.fix:
        sys.exit(run_fix(args.file, args.dry_run))

    cfg = load_config(args.config or str(Path(args.file).parent / ".pine-lint.json"))

    profile = PROFILES[args.profile] if args.profile else PROFILES["all"]
    strict = args.strict or profile["strict"]

    if args.watch:
        return run_watch(args, cfg, profile, strict)

    result = lint_file(args.file, cfg)
    apply_profile(result, profile)

    if args.write_baseline:
        write_baseline(args.write_baseline, Path(args.file).name, result)
        print(f"Wrote {len(result.findings)} finding(s) to {args.write_baseline}")
        sys.exit(0)

    if args.baseline:
        accepted = parse_baseline(args.baseline)
        before = len(result.findings)
        result.findings = [f for f in result.findings if f.code not in accepted]
        suppressed = before - len(result.findings)
        if suppressed and not args.json:
            print(f"({suppressed} finding(s) suppressed by {args.baseline})\n")

    fmt = args.format or ("json" if args.json else "human")
    {"json": print_json, "editor": print_editor,
     "github": print_github, "human": print_human}[fmt](args, result)

    sys.exit(0 if result.ok(strict=strict) else 1)


if __name__ == "__main__":
    try:
        code = main()
        if code is not None:
            sys.exit(code)
    except BrokenPipeError:
        # Common when piping through `head`/`grep` — exit quietly rather than
        # printing a Python traceback.
        sys.stderr.close()
        sys.exit(1)
