#!/usr/bin/env python3
"""
optimize_params.py - Multi-Core Parallel Parameter Grid Optimizer for Pine Script.

Features:
- Executes multi-parameter grid searches across CPU cores using multiprocessing
- Calculates institutional performance metrics (Sharpe, Sortino, Max Drawdown, Profit Factor, Win Rate)
- Generates JSON summary & formatted comparison matrix for optimal parameters

Usage:
    python scripts/optimize_params.py indicators/my_indicator/src/my_indicator.pine \
        --param "Length=10,14,20,30" --param "Multiplier=1.5,2.0,2.5" --bars 500
"""

import argparse
import itertools
import json
import math
import multiprocessing
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from pine_interp import bars_from_csv, synthetic_bars, run_file, Platform


def parse_param_range(param_str: str) -> Tuple[str, List[Any]]:
    """Parses 'Name=val1,val2,val3' or 'Name=start:end:step'."""
    if "=" not in param_str:
        raise ValueError(f"Invalid param format: '{param_str}'. Expected 'Name=val1,val2,val3'")
    key, val_str = param_str.split("=", 1)
    key = key.strip()
    
    values = []
    if ":" in val_str and len(val_str.split(":")) in (2, 3):
        # Range format: start:end or start:end:step
        parts = [float(p.strip()) for p in val_str.split(":")]
        start, end = parts[0], parts[1]
        step = parts[2] if len(parts) == 3 else 1.0
        cur = start
        while cur <= end + 1e-9:
            values.append(int(cur) if cur.is_integer() else round(cur, 4))
            cur += step
    else:
        # Comma-separated format
        for item in val_str.split(","):
            raw = item.strip()
            try:
                values.append(json.loads(raw))
            except json.JSONDecodeError:
                values.append(raw)

    return key, values


def calculate_metrics(bars: List[Dict[str, float]], series_values: List[float]) -> Dict[str, Any]:
    """Calculates quantitative performance metrics on output values/equity."""
    valid_returns = []
    equity = 10000.0
    equity_curve = [equity]
    peak_equity = equity
    max_drawdown_usd = 0.0
    max_drawdown_pct = 0.0

    # Simple trend / signal returns calculation
    trades = 0
    wins = 0
    gross_profit = 0.0
    gross_loss = 0.0

    for i in range(1, len(bars)):
        c_prev = bars[i - 1].get("close", 1.0)
        c_curr = bars[i].get("close", 1.0)
        sig = series_values[i - 1] if i - 1 < len(series_values) else 0

        # Estimate signal return (if numeric signal, else price return)
        ret = (c_curr - c_prev) / (c_prev if c_prev != 0 else 1.0)
        pnl = ret * equity if sig is not None and (sig is True or (isinstance(sig, (int, float)) and sig > 0)) else 0.0

        equity += pnl
        equity_curve.append(round(equity, 2))
        valid_returns.append(pnl / (equity - pnl) if (equity - pnl) > 0 else 0.0)

        if pnl > 0:
            wins += 1
            gross_profit += pnl
            trades += 1
        elif pnl < 0:
            gross_loss += abs(pnl)
            trades += 1

        if equity > peak_equity:
            peak_equity = equity
        dd_usd = peak_equity - equity
        dd_pct = (dd_usd / peak_equity * 100) if peak_equity > 0 else 0
        if dd_usd > max_drawdown_usd:
            max_drawdown_usd = dd_usd
        if dd_pct > max_drawdown_pct:
            max_drawdown_pct = dd_pct

    # Annualized Sharpe & Sortino (assuming daily bars 252 periods)
    mean_ret = sum(valid_returns) / len(valid_returns) if valid_returns else 0.0
    variance = sum((r - mean_ret) ** 2 for r in valid_returns) / len(valid_returns) if valid_returns else 0.0
    std_dev = math.sqrt(variance) if variance > 0 else 1e-6
    
    downside_var = sum((min(0, r) - mean_ret) ** 2 for r in valid_returns) / len(valid_returns) if valid_returns else 0.0
    downside_std = math.sqrt(downside_var) if downside_var > 0 else 1e-6

    sharpe = round((mean_ret / std_dev) * math.sqrt(252), 2)
    sortino = round((mean_ret / downside_std) * math.sqrt(252), 2)
    total_return_pct = round(((equity - 10000.0) / 10000.0) * 100, 2)
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 1.0)
    win_rate_pct = round((wins / trades * 100), 1) if trades > 0 else 0.0

    return {
        "total_return_pct": total_return_pct,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "max_drawdown_usd": round(max_drawdown_usd, 2),
        "profit_factor": profit_factor,
        "win_rate_pct": win_rate_pct,
        "total_trades": trades,
        "final_equity": round(equity, 2),
        "equity_curve": equity_curve[-20:] # sample last 20 for preview
    }


def _worker_eval(task_args):
    file_path, bars, overrides, platform_args = task_args
    try:
        res = run_file(file_path, bars, inputs=overrides, platform=Platform(**platform_args))
        # Pick primary plot or first available plot series
        first_plot_series = next(iter(res.plots.values())) if res.plots else [0.0] * len(bars)
        metrics = calculate_metrics(bars, first_plot_series)
        return {"params": overrides, "metrics": metrics, "ok": True}
    except Exception as e:
        return {"params": overrides, "error": str(e), "ok": False}


def run_optimization(file_path: str, param_ranges: Dict[str, List[Any]], bars: List[Dict[str, float]], processes: int = None) -> List[Dict[str, Any]]:
    """Runs parallel grid search and returns sorted results by Sharpe Ratio and Return."""
    param_keys = list(param_ranges.keys())
    param_combinations = list(itertools.product(*[param_ranges[k] for k in param_keys]))

    tasks = []
    platform_args = {"mintick": 0.01, "timeframe": "60"}
    for comb in param_combinations:
        overrides = {param_keys[i]: comb[i] for i in range(len(param_keys))}
        tasks.append((file_path, bars, overrides, platform_args))

    pool_size = processes or min(multiprocessing.cpu_count(), len(tasks))
    with multiprocessing.Pool(processes=pool_size) as pool:
        results = pool.map(_worker_eval, tasks)

    valid_results = [r for r in results if r["ok"]]
    # Sort by Sharpe ratio descending, then Return descending
    valid_results.sort(key=lambda x: (x["metrics"]["sharpe_ratio"], x["metrics"]["total_return_pct"]), reverse=True)
    return valid_results


def main():
    parser = argparse.ArgumentParser(description="Multi-Core Parameter Optimizer for Pine Script.")
    parser.add_argument("file", help="Pine Script file to optimize")
    parser.add_argument("--param", action="append", required=True, help="Parameter definition, e.g. 'Length=10,20,50' or 'Mult=1.0:3.0:0.5'")
    parser.add_argument("--bars", type=int, default=400, help="Synthetic bars count (default 400)")
    parser.add_argument("--csv", help="Optional CSV file with real market data")
    parser.add_argument("--workers", type=int, default=None, help="Number of CPU workers (default: auto)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    param_ranges = {}
    for p in args.param:
        k, vals = parse_param_range(p)
        param_ranges[k] = vals

    bars = bars_from_csv(args.csv) if args.csv else synthetic_bars(args.bars, seed=42)
    print(f"Starting grid search on {len(bars)} bars across {multiprocessing.cpu_count()} CPU cores...", file=sys.stderr)

    results = run_optimization(args.file, param_ranges, bars, processes=args.workers)

    if args.json:
        print(json.dumps({"total_runs": len(results), "top_results": results[:20]}, indent=2))
        return

    print(f"\nOptimization Results for {args.file} (Total Combinations: {len(results)}):\n")
    print(f"{'Rank':<5} {'Parameters':<35} {'Return %':<10} {'Sharpe':<8} {'MaxDD %':<10} {'WinRate %':<10} {'ProfitFactor':<12}")
    print("-" * 95)

    for i, res in enumerate(results[:15]):
        p_str = ", ".join(f"{k}={v}" for k, v in res["params"].items())
        m = res["metrics"]
        print(f"#{i+1:<4} {p_str:<35} {m['total_return_pct']:<10.2f} {m['sharpe_ratio']:<8.2f} {m['max_drawdown_pct']:<10.2f} {m['win_rate_pct']:<10.1f} {m['profit_factor']:<12.2f}")


if __name__ == "__main__":
    main()
