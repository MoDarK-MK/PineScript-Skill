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
}

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
}

STRATEGY_ORDER_FUNCS = [
    "strategy.entry(", "strategy.order(", "strategy.exit(", "strategy.close(",
    "strategy.close_all(", "strategy.cancel(", "strategy.cancel_all(",
]
TRANSP_FUNCS = ["bgcolor(", "fill(", "plot(", "plotarrow(", "plotchar(", "plotshape("]
PLOT_COUNT_FUNCS = [
    "plot(", "plotarrow(", "plotbar(", "plotcandle(", "plotchar(", "plotshape(",
    "alertcondition(", "bgcolor(", "barcolor(", "fill(",
]
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


class LintResult:
    def __init__(self):
        self.findings = []

    def add(self, line_no, code, msg):
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
    """Remove // comments AND blank out string contents (quotes included).
    Use this for structural checks (brackets, keywords, param names) where
    string contents would create false positives."""
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
            i += 1
            continue
        if ch in ('"', "'"):
            in_str = ch
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


def check_declaration(text, result):
    has_indicator = bool(re.search(r'\bindicator\s*\(', text))
    has_strategy = bool(re.search(r'\bstrategy\s*\(', text))
    has_library = bool(re.search(r'\blibrary\s*\(', text))
    if not (has_indicator or has_strategy or has_library):
        result.add(0, "PINE002", "No indicator(), strategy(), or library() declaration found.")
        return
    if (has_indicator or has_strategy) and "overlay=" not in text and "overlay =" not in text:
        result.add(0, "PINE022", "indicator()/strategy() doesn't set overlay= explicitly.")
    if has_strategy:
        missing = [p for p in ("default_qty_type", "default_qty_value", "commission_")
                   if p not in text]
        if missing:
            result.add(0, "PINE021",
                        "strategy() call doesn't set " + ", ".join(missing) + " — engine defaults "
                        "will silently shape backtest results (v6 defaults margin_long/short to 100, "
                        "so at least funds/margin are realistic by default, but sizing/commission still "
                        "need explicit values for a meaningful backtest).")


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


def check_var_accumulator(lines, result):
    var_declared = set()
    for i, raw_line in enumerate(lines):
        line = strip_strings_and_comments(raw_line)
        m_decl = re.match(r'\s*var(?:ip)?\s+\w*\s*(\w+)\s*=', line)
        if m_decl:
            var_declared.add(m_decl.group(1))
            continue
        m_self = re.match(r'\s*(\w+)\s*:?=\s*\1\s*[\+\-\*/]', line)
        if m_self:
            name = m_self.group(1)
            if name not in var_declared:
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


def check_block_headers_have_bodies(lines, result):
    stripped_lines = [strip_strings_and_comments(l) for l in lines]
    n = len(lines)
    for i in range(n):
        trimmed = stripped_lines[i].strip()
        if not trimmed:
            continue
        is_header = bool(HEADER_KEYWORD_RE.search(trimmed)) or bool(ARROW_END_RE.search(trimmed))
        if not is_header:
            continue
        header_indent = indent_width(lines[i])
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
    plot_count = sum(text.count(f) for f in PLOT_COUNT_FUNCS)
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
    check_declaration(text, result)
    check_has_output(text, result)
    check_balanced_delimiters(lines, result)
    check_deprecated_syntax(lines, result)
    check_security_lookahead(statements, result, cfg)
    check_var_accumulator(lines, result)
    check_line_length(lines, result, cfg)
    check_inputs_have_titles(statements, result)
    check_when_removed(statements, result)
    check_transp_removed(statements, result)
    check_linewidth_minimum(statements, result)
    check_switch_default(lines, result)
    check_history_on_literal(lines, result)
    check_duplicate_named_params(statements, result)
    check_timeframe_period_compare(lines, result)
    check_lazy_eval_trap(statements, result)
    check_naming_convention(statements, lines, result)
    check_indentation(lines, result)
    check_block_headers_have_bodies(lines, result)
    check_int_division_literals(lines, result)
    check_plot_and_drawing_limits(text, lines, result, cfg)

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


def main():
    parser = argparse.ArgumentParser(description="Rule-based offline linter for Pine Script.")
    parser.add_argument("file", nargs="?", help="Path to a .pine file")
    parser.add_argument("--config", default=None, help="Path to a .pine-lint.json config override")
    parser.add_argument("--json", action="store_true", help="Emit findings as JSON")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures (exit 1)")
    parser.add_argument("--list-rules", action="store_true", help="Print the full rule catalog and exit")
    args = parser.parse_args()

    if args.list_rules:
        for code in sorted(RULES):
            sev, summary = RULES[code]
            print(f"{code}\t{sev:8s}\t{summary}")
        sys.exit(0)

    if not args.file:
        parser.error("the following arguments are required: file (unless --list-rules)")

    if not Path(args.file).exists():
        print(f"error: file not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    cfg = load_config(args.config or str(Path(args.file).parent / ".pine-lint.json"))
    result = lint_file(args.file, cfg)

    if args.json:
        print_json(args, result)
    else:
        print_human(args, result)

    sys.exit(0 if result.ok(strict=args.strict) else 1)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        # Common when piping through `head`/`grep` — exit quietly rather than
        # printing a Python traceback.
        sys.stderr.close()
        sys.exit(1)
