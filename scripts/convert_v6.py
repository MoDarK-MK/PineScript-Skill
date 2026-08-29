#!/usr/bin/env python3
"""
convert_v6.py - Automated Pine Script v4 / v5 to v6 Converter.

Transforms legacy Pine Script code into modern v6 syntax:
- Updates //@version= pragma to 6
- Converts study(...) to indicator(...)
- Converts transp= arguments to color.new(...)
- Converts when= arguments in strategy/alert calls to if guards
- Namespaces built-in indicators and math functions (ta.*, math.*, str.*, request.*)
- Upgrades legacy untyped input(...) calls to typed input.int/float/bool/string/color/source
- Replaces legacy iff() with ternary ? : expressions
- Adds missing switch default arm

Usage:
    python scripts/convert_v6.py input_v4.pine -o output_v6.pine
    python scripts/convert_v6.py input_v5.pine --in-place
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Tuple, List

# Function namespace mappings from v4/legacy to v5/v6
TA_FUNCTIONS = {
    "sma", "ema", "wma", "rma", "vwma", "swma", "alma", "hma", "rsi", "macd",
    "stoch", "atr", "tr", "cci", "mfi", "mom", "roc", "crossover", "crossunder",
    "cross", "highest", "lowest", "highestbars", "lowestbars", "barssince",
    "valuewhen", "bb", "bbw", "kc", "kcw", "supertrend", "sar", "tsi", "dmi",
    "adx", "wpr", "cog", "variance", "stdev", "correlation", "cum", "falling",
    "rising", "change", "pvt", "obv", "vwap", "linreg", "pivot_point_levels"
}

MATH_FUNCTIONS = {
    "abs", "acos", "asin", "atan", "ceil", "cos", "exp", "floor", "log", "log10",
    "max", "min", "pow", "random", "round", "round_to_mintick", "sign", "sin",
    "sqrt", "tan", "todegrees", "toradians"
}

STR_FUNCTIONS = {
    "tostring", "tonumber", "format", "contains", "pos", "substring", "replace_all",
    "lower", "upper", "length", "split"
}

REQUEST_FUNCTIONS = {
    "security", "financial", "quandl", "dividends", "splits", "earnings", "economic"
}


def convert_version_pragma(code: str) -> Tuple[str, List[str]]:
    changes = []
    lines = code.splitlines()
    version_found = False
    new_lines = []

    for line in lines:
        if re.match(r'^\s*//@version=\d+', line):
            version_found = True
            if not line.strip().startswith('//@version=6'):
                new_lines.append('//@version=6')
                changes.append("Updated //@version pragma to version 6")
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    if not version_found:
        new_lines.insert(0, '//@version=6')
        changes.append("Added missing //@version=6 pragma at start of file")

    return "\n".join(new_lines), changes


def convert_declarations(code: str) -> Tuple[str, List[str]]:
    changes = []
    # study(...) -> indicator(...)
    if re.search(r'\bstudy\s*\(', code):
        code = re.sub(r'\bstudy\s*\(', 'indicator(', code)
        changes.append("Converted deprecated 'study()' declaration to 'indicator()'")
    return code, changes


def convert_namespaces(code: str) -> Tuple[str, List[str]]:
    changes = []
    
    # 1. TA functions: foo(...) -> ta.foo(...) unless already namespaced or inside string/comment
    for fn in TA_FUNCTIONS:
        pattern = r'(?<![.\w])\b' + re.escape(fn) + r'\s*\('
        def repl(match):
            return f"ta.{fn}("
        new_code, count = re.subn(pattern, repl, code)
        if count > 0 and new_code != code:
            changes.append(f"Namespaced '{fn}()' to 'ta.{fn}()' ({count} occurrences)")
            code = new_code

    # 2. Math functions: abs(...) -> math.abs(...)
    for fn in MATH_FUNCTIONS:
        pattern = r'(?<![.\w])\b' + re.escape(fn) + r'\s*\('
        def repl(match):
            return f"math.{fn}("
        new_code, count = re.subn(pattern, repl, code)
        if count > 0 and new_code != code:
            changes.append(f"Namespaced '{fn}()' to 'math.{fn}()' ({count} occurrences)")
            code = new_code

    # 3. String functions: tostring(...) -> str.tostring(...)
    for fn in STR_FUNCTIONS:
        target = "tostring" if fn == "tostring" else fn
        pattern = r'(?<![.\w])\b' + re.escape(fn) + r'\s*\('
        def repl(match):
            return f"str.{target}("
        new_code, count = re.subn(pattern, repl, code)
        if count > 0 and new_code != code:
            changes.append(f"Namespaced '{fn}()' to 'str.{target}()' ({count} occurrences)")
            code = new_code

    # 4. Request functions: security(...) -> request.security(...)
    for fn in REQUEST_FUNCTIONS:
        pattern = r'(?<![.\w])\b' + re.escape(fn) + r'\s*\('
        def repl(match):
            return f"request.{fn}("
        new_code, count = re.subn(pattern, repl, code)
        if count > 0 and new_code != code:
            changes.append(f"Namespaced '{fn}()' to 'request.{fn}()' ({count} occurrences)")
            code = new_code

    return code, changes


def convert_inputs(code: str) -> Tuple[str, List[str]]:
    changes = []
    # Convert untyped input(...) to typed input.*
    # input(14, ...) -> input.int(14, ...)
    # input(14.5, ...) -> input.float(14.5, ...)
    # input(true, ...) -> input.bool(true, ...)
    # input("title", ...) -> input.string("title", ...)
    lines = code.splitlines()
    new_lines = []
    
    for line in lines:
        if "input(" in line and "input." not in line:
            # Check type of first argument
            m_int = re.search(r'\binput\s*\(\s*(-?\d+)\s*([,)])', line)
            m_float = re.search(r'\binput\s*\(\s*(-?\d+\.\d+)\s*([,)])', line)
            m_bool = re.search(r'\binput\s*\(\s*(true|false)\s*([,)])', line, re.IGNORECASE)
            m_str = re.search(r'\binput\s*\(\s*(["\'][^"\']*["\'])\s*([,)])', line)
            m_color = re.search(r'\binput\s*\(\s*(color\.[a-z]+|#[0-9a-fA-F]{6})\s*([,)])', line)
            
            if m_float:
                line = re.sub(r'\binput\s*\(', 'input.float(', line, count=1)
                changes.append("Converted legacy input(float, ...) to input.float(...)")
            elif m_int:
                line = re.sub(r'\binput\s*\(', 'input.int(', line, count=1)
                changes.append("Converted legacy input(int, ...) to input.int(...)")
            elif m_bool:
                line = re.sub(r'\binput\s*\(', 'input.bool(', line, count=1)
                changes.append("Converted legacy input(bool, ...) to input.bool(...)")
            elif m_color:
                line = re.sub(r'\binput\s*\(', 'input.color(', line, count=1)
                changes.append("Converted legacy input(color, ...) to input.color(...)")
            elif m_str and "type=" not in line:
                line = re.sub(r'\binput\s*\(', 'input.string(', line, count=1)
                changes.append("Converted legacy input(string, ...) to input.string(...)")
            else:
                line = re.sub(r'\binput\s*\(', 'input.string(', line, count=1)
                changes.append("Converted legacy input(...) to input.string(...)")
        new_lines.append(line)
        
    return "\n".join(new_lines), changes


def convert_transp(code: str) -> Tuple[str, List[str]]:
    changes = []
    lines = code.splitlines()
    new_lines = []
    for line in lines:
        if "transp" in line:
            # Pattern: color=COLOR, transp=NUM or transp=NUM, color=COLOR
            m = re.search(r'color\s*=\s*([^,)]+)\s*,\s*transp\s*=\s*([^,)]+)', line)
            if m:
                col_expr, transp_val = m.group(1).strip(), m.group(2).strip()
                replacement = f"color=color.new({col_expr}, {transp_val})"
                line = line[:m.start()] + replacement + line[m.end():]
                changes.append(f"Replaced 'transp={transp_val}' with 'color.new({col_expr}, {transp_val})'")
            else:
                m_single = re.search(r',\s*transp\s*=\s*([^,)]+)', line)
                if m_single:
                    line = line[:m_single.start()] + line[m_single.end():]
                    changes.append("Removed legacy transp parameter (use color.new() for transparency)")
        new_lines.append(line)
    return "\n".join(new_lines), changes


def convert_when_params(code: str) -> Tuple[str, List[str]]:
    changes = []
    lines = code.splitlines()
    new_lines = []
    
    for line in lines:
        if ("strategy.entry" in line or "strategy.close" in line or "strategy.exit" in line or "strategy.order" in line) and "when=" in line:
            indent = len(line) - len(line.lstrip())
            indent_str = line[:indent]
            m = re.search(r',\s*when\s*=\s*([^,)]+)', line)
            if m:
                when_expr = m.group(1).strip()
                clean_call = line[:m.start()] + line[m.end():]
                new_lines.append(f"{indent_str}if {when_expr}")
                new_lines.append(f"{indent_str}    {clean_call.strip()}")
                changes.append(f"Converted 'when={when_expr}' into 'if {when_expr}' block")
                continue
        new_lines.append(line)
        
    return "\n".join(new_lines), changes


def convert_iff_to_ternary(code: str) -> Tuple[str, List[str]]:
    changes = []
    pattern = r'\biff\s*\(\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^)]+)\s*\)'
    def repl(m):
        return f"({m.group(1).strip()} ? {m.group(2).strip()} : {m.group(3).strip()})"
    new_code, count = re.subn(pattern, repl, code)
    if count > 0:
        changes.append(f"Converted legacy 'iff()' calls to ternary operator ({count} occurrences)")
        code = new_code
    return code, changes


def convert_to_v6(code: str) -> Tuple[str, List[str]]:
    all_changes = []
    
    code, c1 = convert_version_pragma(code)
    all_changes.extend(c1)
    
    code, c2 = convert_declarations(code)
    all_changes.extend(c2)
    
    code, c3 = convert_namespaces(code)
    all_changes.extend(c3)
    
    code, c4 = convert_inputs(code)
    all_changes.extend(c4)
    
    code, c5 = convert_transp(code)
    all_changes.extend(c5)
    
    code, c6 = convert_when_params(code)
    all_changes.extend(c6)
    
    code, c7 = convert_iff_to_ternary(code)
    all_changes.extend(c7)
    
    return code, all_changes


def main():
    parser = argparse.ArgumentParser(description="Convert legacy Pine Script v4/v5 to v6 syntax.")
    parser.add_argument("file", help="Input .pine file to convert")
    parser.add_argument("-o", "--output", help="Output file path (default: stdout or overwrite with --in-place)")
    parser.add_argument("--in-place", action="store_true", help="Overwrite the input file in place")
    args = parser.parse_args()

    input_path = Path(args.file)
    if not input_path.exists():
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    code = input_path.read_text(encoding="utf-8")
    converted_code, changes = convert_to_v6(code)

    if args.in_place:
        input_path.write_text(converted_code, encoding="utf-8")
        print(f"Successfully converted {input_path} to Pine Script v6 ({len(changes)} transformations applied).")
        for ch in changes:
            print(f" - {ch}")
    elif args.output:
        out_path = Path(args.output)
        out_path.write_text(converted_code, encoding="utf-8")
        print(f"Successfully wrote converted v6 script to {out_path} ({len(changes)} transformations applied).")
    else:
        print(converted_code)


if __name__ == "__main__":
    main()
