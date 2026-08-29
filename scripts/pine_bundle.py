#!/usr/bin/env python3
"""
pine_bundle.py - Standalone Inliner and Tree-Shaker for Pine Script Libraries.

Pine Script libraries require publishing before other scripts can import them.
pine_bundle resolves `import ... as alias` statements or `pt.*` helper calls by:
1. Finding which functions from local libraries (e.g., libraries/pine_toolkit) are actually used.
2. Inlining only the referenced functions (Tree-shaking).
3. Stripping the 'export' keyword and rewiring calls.
4. Producing a 100% self-contained standalone .pine file ready for instant pasting.

Usage:
    python scripts/pine_bundle.py indicators/my_indicator/src/my_indicator.pine -o release/bundle.pine
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, Set, Tuple, List

ROOT = Path(__file__).resolve().parent.parent
LIBRARIES_DIR = ROOT / "libraries"


def parse_library_exports(lib_path: Path) -> Dict[str, str]:
    """Parses a library .pine file and returns a mapping of function_name -> function_code_block."""
    if not lib_path.exists():
        return {}

    content = lib_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    exports = {}
    
    current_fn = None
    fn_lines = []
    
    for line in lines:
        # Match export function signature: export fnName(...) =>
        m = re.match(r'^\s*export\s+([a-zA-Z_]\w*)\s*\(', line)
        if m:
            if current_fn:
                exports[current_fn] = "\n".join(fn_lines)
            current_fn = m.group(1)
            # Remove 'export' keyword from the signature
            clean_sig = re.sub(r'^\s*export\s+', '', line)
            fn_lines = [clean_sig]
        elif current_fn:
            # Check if we are still inside the indented function body or comments
            if line.startswith("    ") or line.startswith("\t") or line.strip().startswith("//") or not line.strip():
                fn_lines.append(line)
            else:
                # End of function
                exports[current_fn] = "\n".join(fn_lines).rstrip()
                current_fn = None
                fn_lines = []
                
    if current_fn and fn_lines:
        exports[current_fn] = "\n".join(fn_lines).rstrip()

    return exports


def bundle_script(source_code: str, lib_name: str = "pine_toolkit") -> Tuple[str, List[str]]:
    """Tree-shakes and inlines library dependencies into a standalone script."""
    lib_file = LIBRARIES_DIR / lib_name / "src" / f"{lib_name}.pine"
    if not lib_file.exists():
        # Search for any library file matching name
        matches = list(LIBRARIES_DIR.glob(f"**/{lib_name}.pine"))
        if matches:
            lib_file = matches[0]
        else:
            return source_code, [f"Warning: Library {lib_name} not found in {LIBRARIES_DIR}"]

    library_functions = parse_library_exports(lib_file)
    bundled_functions = []
    
    # Check for imports like: import User/PineToolkit/1 as pt
    import_pattern = r'^\s*import\s+[^\n]+as\s+([a-zA-Z_]\w*)'
    alias = "pt"
    m_import = re.search(import_pattern, source_code, re.MULTILINE)
    if m_import:
        alias = m_import.group(1)
        # Remove import line
        source_code = re.sub(import_pattern, '', source_code, flags=re.MULTILINE)

    # Detect which functions are called: alias.fnName(...) or direct fnName(...)
    needed_fns: Set[str] = set()
    for fn in library_functions:
        if re.search(r'\b' + re.escape(alias) + r'\.' + re.escape(fn) + r'\s*\(', source_code):
            needed_fns.add(fn)
        elif re.search(r'(?<![.\w])\b' + re.escape(fn) + r'\s*\(', source_code):
            needed_fns.add(fn)

    if not needed_fns:
        return source_code, ["No external library functions needed to be inlined."]

    # Replace alias.fnName(...) with fnName(...)
    for fn in needed_fns:
        source_code = re.sub(r'\b' + re.escape(alias) + r'\.' + re.escape(fn) + r'\b', fn, source_code)
        bundled_functions.append(library_functions[fn])

    # Inject inlined functions after declaration
    injection_block = "\n// ————— Inlined Helper Functions (Bundled via PineScript-Skill) —————\n" + \
                      "\n\n".join(bundled_functions) + "\n\n"

    # Find position after //@version and indicator()/strategy()
    lines = source_code.splitlines()
    insert_idx = 0
    for i, l in enumerate(lines):
        if re.match(r'^\s*(indicator|strategy|library)\s*\(', l):
            insert_idx = i + 1
            break

    final_lines = lines[:insert_idx] + [injection_block] + lines[insert_idx:]
    final_code = "\n".join(final_lines)

    logs = [f"Inlined {len(needed_fns)} functions from {lib_name}: {', '.join(sorted(needed_fns))}"]
    return final_code, logs


def main():
    parser = argparse.ArgumentParser(description="Bundle and tree-shake Pine Script libraries into standalone scripts.")
    parser.add_argument("file", help="Source .pine file with library dependencies")
    parser.add_argument("-o", "--output", help="Output file path (default: stdout)")
    parser.add_argument("--lib", default="pine_toolkit", help="Library name to inline (default: pine_toolkit)")
    args = parser.parse_args()

    src_path = Path(args.file)
    if not src_path.exists():
        print(f"Error: file not found: {src_path}", file=sys.stderr)
        sys.exit(1)

    code = src_path.read_text(encoding="utf-8")
    bundled_code, logs = bundle_script(code, args.lib)

    for log in logs:
        print(f"[pine_bundle] {log}", file=sys.stderr)

    if args.output:
        out_p = Path(args.output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(bundled_code, encoding="utf-8")
        print(f"Successfully wrote bundled script to {out_p}")
    else:
        print(bundled_code)


if __name__ == "__main__":
    main()
