#!/usr/bin/env python3
"""
inspect_mtf.py - Advanced Multi-Timeframe (MTF) Repainting Inspector & Visualizer.

Analyzes request.security() calls, looks for future data leakage (lookahead traps),
unconfirmed realtime bar reads, and produces a visual execution timeline showing
how HTF bars project onto LTF chart bars.

Usage:
    python scripts/inspect_mtf.py indicators/my_indicator/src/my_indicator.pine
    python scripts/inspect_mtf.py script.pine --json
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Any


def analyze_security_calls(code: str) -> List[Dict[str, Any]]:
    findings = []
    lines = code.splitlines()

    for idx, raw in enumerate(lines):
        line_no = idx + 1
        line = raw.strip()

        # Match request.security or legacy security
        if not re.search(r'\b(request\.)?security\s*\(', line):
            continue

        # Extract arguments
        lookahead_on = bool(re.search(r'barmerge\.lookahead_on\b', line))
        lookahead_off = bool(re.search(r'barmerge\.lookahead_off\b', line))
        lookahead_missing = not (lookahead_on or lookahead_off)

        # Check expression inside call
        has_bar_offset = bool(re.search(r'\[\s*\d+\s*\]', line))
        reads_close = bool(re.search(r'\bclose\b', line))
        reads_high_low = bool(re.search(r'\b(high|low|hl2|hlc3|ohlc4)\b', line))
        
        # Extract timeframe if possible
        tf_match = re.search(r'security\s*\([^,]+,\s*([^,]+),', line)
        tf_expr = tf_match.group(1).strip() if tf_match else "unknown"

        # Risk assessment
        risk_level = "SAFE"
        verdict = []
        recommendation = ""
        timeline_leak = False

        if lookahead_on:
            if not has_bar_offset and (reads_close or reads_high_low):
                risk_level = "CRITICAL_REPAINT"
                verdict.append("DANGEROUS: lookahead_on used with unshifted price series (e.g. close).")
                verdict.append("Historical bars will read future closing price BEFORE the higher bar actually closes!")
                recommendation = "Shift the expression inside security: e.g. request.security(sym, tf, close[1], lookahead=barmerge.lookahead_on)"
                timeline_leak = True
            else:
                risk_level = "LOW_RISK_OFFSET"
                verdict.append("lookahead_on used with offset [1]. This is safe for reading previous closed HTF bar at the open of the first LTF bar.")
        elif lookahead_off:
            verdict.append("lookahead_off: Standard behavior. No historical future leak.")
            if reads_close:
                verdict.append("Note: On realtime/unconfirmed bars, HTF value will update tick-by-tick until the HTF bar closes.")
        elif lookahead_missing:
            risk_level = "WARN_DEFAULT_LOOKAHEAD"
            verdict.append("lookahead parameter is omitted. Pine Script defaults to lookahead_off, but explicit declaration is recommended.")
            recommendation = "Add explicit 'lookahead = barmerge.lookahead_off'"

        findings.append({
            "line": line_no,
            "code_snippet": line,
            "timeframe": tf_expr,
            "risk_level": risk_level,
            "lookahead_on": lookahead_on,
            "lookahead_off": lookahead_off,
            "has_offset": has_bar_offset,
            "timeline_leak": timeline_leak,
            "verdict": verdict,
            "recommendation": recommendation
        })

    return findings


def generate_ascii_timeline(findings: List[Dict[str, Any]]) -> str:
    """Generates an ASCII visualization showing how HTF and LTF bars align."""
    has_leak = any(f["timeline_leak"] for f in findings)
    
    timeline = []
    timeline.append("┌────────────────────────────────────────────────────────────────────────┐")
    timeline.append("│                      MTF EXECUTION TIMELINE SIMULATOR                  │")
    timeline.append("└────────────────────────────────────────────────────────────────────────┘")
    timeline.append("")
    timeline.append("HTF (e.g. 1-Hour Bar):")
    timeline.append("├─────────────────────────────────────────────────────────────────────────┤ (Closes at T+60)")
    timeline.append("│                             1-Hour Candle                               │")
    timeline.append("└─────────────────────────────────────────────────────────────────────────┘")
    timeline.append("")
    timeline.append("LTF (e.g. 15-Min Chart Bars):")
    timeline.append("┌──────────────┬──────────────┬──────────────┬──────────────┐")
    timeline.append("│  Bar 1 (00)  │  Bar 2 (15)  │  Bar 3 (30)  │  Bar 4 (45)  │")
    timeline.append("└──────────────┴──────────────┴──────────────┴──────────────┘")
    
    if has_leak:
        timeline.append("\n⚠️  REPAINTING / FUTURE DATA LEAKAGE DETECTED:")
        timeline.append("   At Bar 1 (00): Script accesses 1-Hour close price of Bar 4 (45)!")
        timeline.append("   [Bar 1] <------------------ FUTURE DATA INJECTION (T+60 Close) [Bar 4]")
        timeline.append("   Result: Strategy will execute perfect trades in historical backtest that are IMPOSSIBLE in live trading.")
    else:
        timeline.append("\n✅  NO HISTORICAL FUTURE LEAKAGE DETECTED:")
        timeline.append("   At Bar 1 (00): Script reads previous confirmed 1-Hour bar close.")
        timeline.append("   Current 1-Hour bar values only become final after Bar 4 finishes.")

    return "\n".join(timeline)


def inspect_mtf(file_path: str) -> Dict[str, Any]:
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}", "calls": []}

    code = path.read_text(encoding="utf-8")
    calls = analyze_security_calls(code)
    timeline = generate_ascii_timeline(calls)

    return {
        "file": str(path),
        "total_calls": len(calls),
        "has_repainting_risk": any(c["risk_level"] == "CRITICAL_REPAINT" for c in calls),
        "calls": calls,
        "timeline_visualization": timeline
    }


def main():
    parser = argparse.ArgumentParser(description="Multi-Timeframe Repainting Inspector for Pine Script.")
    parser.add_argument("file", help="Path to .pine file")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    result = inspect_mtf(args.file)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\nMTF Repainting Analysis for: {result['file']}")
        print(f"Total security calls found: {result['total_calls']}\n")
        
        for c in result["calls"]:
            badge = "[CRITICAL REPAINT]" if c["risk_level"] == "CRITICAL_REPAINT" else f"[{c['risk_level']}]"
            print(f"Line {c['line']}: {badge}")
            print(f"  Code: {c['code_snippet']}")
            for v in c["verdict"]:
                print(f"  • {v}")
            if c["recommendation"]:
                print(f"  💡 Fix: {c['recommendation']}")
            print()

        print(result["timeline_visualization"])


if __name__ == "__main__":
    main()
