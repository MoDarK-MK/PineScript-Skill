import os
import subprocess
import tempfile
import json
import urllib.request
import urllib.error
import math
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="PineScript-Skill App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = ROOT / "scripts"
SKILL_PATH = ROOT / "SKILL.md"


def read_skill():
    if not SKILL_PATH.exists():
        return "You are an AI assistant for TradingView Pine Script v6 development."
    return SKILL_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Linting & Code Fixing
# ---------------------------------------------------------------------------
@app.post("/api/lint")
async def lint_code(request: Request):
    data = await request.json()
    code = data.get("code", "")
    with tempfile.NamedTemporaryFile(suffix=".pine", delete=False, mode="w", encoding="utf-8") as f:
        f.write(code)
        temp_path = f.name

    try:
        lint_cmd = ["python", str(SCRIPTS_DIR / "pine_lint.py"), temp_path, "--json"]
        result = subprocess.run(lint_cmd, capture_output=True, text=True, encoding="utf-8")
        try:
            output_json = json.loads(result.stdout)
            return JSONResponse(output_json)
        except json.JSONDecodeError:
            return JSONResponse({"error": "Failed to parse linter output", "raw": result.stdout, "stderr": result.stderr})
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.post("/api/lint/fix")
async def fix_code(request: Request):
    data = await request.json()
    code = data.get("code", "")
    with tempfile.NamedTemporaryFile(suffix=".pine", delete=False, mode="w", encoding="utf-8") as f:
        f.write(code)
        temp_path = f.name

    try:
        fix_cmd = ["python", str(SCRIPTS_DIR / "pine_lint.py"), temp_path, "--fix"]
        result = subprocess.run(fix_cmd, capture_output=True, text=True, encoding="utf-8")
        fixed_code = Path(temp_path).read_text(encoding="utf-8")
        return JSONResponse({"fixed_code": fixed_code, "logs": result.stdout})
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.get("/api/explain/{code}")
async def explain_error(code: str):
    try:
        lint_cmd = ["python", str(SCRIPTS_DIR / "pine_lint.py"), "--explain", code]
        result = subprocess.run(lint_cmd, capture_output=True, text=True, encoding="utf-8")
        if result.returncode == 0:
            return JSONResponse({"explanation": result.stdout})
        return JSONResponse({"error": result.stderr or result.stdout})
    except Exception as e:
        return JSONResponse({"error": str(e)})


# ---------------------------------------------------------------------------
# Multi-Provider AI Chat & Generation
# ---------------------------------------------------------------------------
@app.post("/api/chat")
async def chat(request: Request):
    data = await request.json()
    prompt = data.get("prompt", "")
    provider = data.get("provider", "ollama").lower()
    model = data.get("model", "llama3.1")
    api_key = data.get("api_key", "")
    host = data.get("host", "http://localhost:11434")
    system_prompt = read_skill()

    def generate():
        try:
            if provider == "ollama":
                url = f"{host}/api/chat"
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": True
                }
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=60) as response:
                    for line in response:
                        if line:
                            chunk = json.loads(line)
                            if "message" in chunk and "content" in chunk["message"]:
                                yield chunk["message"]["content"]
                            if chunk.get("done"):
                                break

            elif provider in ("openai", "deepseek", "custom"):
                endpoint = "https://api.openai.com/v1/chat/completions" if provider == "openai" else \
                           ("https://api.deepseek.com/chat/completions" if provider == "deepseek" else f"{host}/chat/completions")
                
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": True
                }
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                }
                req = urllib.request.Request(
                    endpoint,
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=60) as response:
                    for line in response:
                        line_str = line.decode("utf-8").strip()
                        if line_str.startswith("data: "):
                            data_part = line_str[6:].strip()
                            if data_part == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_part)
                                delta = chunk["choices"][0].get("delta", {})
                                if "content" in delta and delta["content"]:
                                    yield delta["content"]
                            except Exception:
                                pass

            elif provider == "anthropic":
                endpoint = "https://api.anthropic.com/v1/messages"
                payload = {
                    "model": model or "claude-3-5-sonnet-20241022",
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 4096,
                    "stream": True
                }
                headers = {
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01"
                }
                req = urllib.request.Request(
                    endpoint,
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=60) as response:
                    for line in response:
                        line_str = line.decode("utf-8").strip()
                        if line_str.startswith("data: "):
                            try:
                                chunk = json.loads(line_str[6:])
                                if chunk.get("type") == "content_block_delta":
                                    yield chunk.get("delta", {}).get("text", "")
                            except Exception:
                                pass
            else:
                yield f"Error: Unknown provider '{provider}'."

        except Exception as e:
            yield f"\n[AI Error]: Could not complete request via {provider} ({str(e)}). Ensure API key or Ollama daemon is running."

    return StreamingResponse(generate(), media_type="text/plain")


@app.get("/api/models")
async def get_models(provider: str = "ollama", host: str = "http://localhost:11434"):
    if provider == "ollama":
        url = f"{host}/api/tags"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as response:
                data = json.loads(response.read())
                models = [m["name"] for m in data.get("models", [])]
                return JSONResponse({"models": models})
        except Exception:
            return JSONResponse({"models": ["llama3.1", "qwen2.5-coder", "deepseek-r1:8b", "mistral"]})
    elif provider == "openai":
        return JSONResponse({"models": ["gpt-4o", "gpt-4o-mini", "o3-mini", "gpt-4-turbo"]})
    elif provider == "anthropic":
        return JSONResponse({"models": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"]})
    elif provider == "deepseek":
        return JSONResponse({"models": ["deepseek-chat", "deepseek-reasoner"]})
    return JSONResponse({"models": ["default"]})


# ---------------------------------------------------------------------------
# Converter, MTF Repainting Inspector & Bundler
# ---------------------------------------------------------------------------
@app.post("/api/convert-v6")
async def convert_v6(request: Request):
    data = await request.json()
    code = data.get("code", "")
    with tempfile.NamedTemporaryFile(suffix=".pine", delete=False, mode="w", encoding="utf-8") as f:
        f.write(code)
        temp_path = f.name

    try:
        conv_cmd = ["python", str(SCRIPTS_DIR / "convert_v6.py"), temp_path]
        result = subprocess.run(conv_cmd, capture_output=True, text=True, encoding="utf-8")
        return JSONResponse({"converted_code": result.stdout, "stderr": result.stderr})
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.post("/api/inspect-mtf")
async def inspect_mtf_api(request: Request):
    data = await request.json()
    code = data.get("code", "")
    with tempfile.NamedTemporaryFile(suffix=".pine", delete=False, mode="w", encoding="utf-8") as f:
        f.write(code)
        temp_path = f.name

    try:
        mtf_cmd = ["python", str(SCRIPTS_DIR / "inspect_mtf.py"), temp_path, "--json"]
        result = subprocess.run(mtf_cmd, capture_output=True, text=True, encoding="utf-8")
        try:
            return JSONResponse(json.loads(result.stdout))
        except Exception:
            return JSONResponse({"error": "Failed to parse MTF analysis", "raw": result.stdout, "stderr": result.stderr})
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.post("/api/bundle")
async def bundle_code(request: Request):
    data = await request.json()
    code = data.get("code", "")
    with tempfile.NamedTemporaryFile(suffix=".pine", delete=False, mode="w", encoding="utf-8") as f:
        f.write(code)
        temp_path = f.name

    try:
        bundle_cmd = ["python", str(SCRIPTS_DIR / "pine_bundle.py"), temp_path]
        result = subprocess.run(bundle_cmd, capture_output=True, text=True, encoding="utf-8")
        return JSONResponse({"bundled_code": result.stdout, "logs": result.stderr})
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ---------------------------------------------------------------------------
# Backtesting & Parameter Optimization
# ---------------------------------------------------------------------------
@app.post("/api/run")
async def run_pine_code(request: Request):
    data = await request.json()
    code = data.get("code", "")
    bars_count = int(data.get("bars", 300))
    with tempfile.NamedTemporaryFile(suffix=".pine", delete=False, mode="w", encoding="utf-8") as f:
        f.write(code)
        temp_path = f.name

    try:
        # Import pine_interp locally
        import sys
        if str(SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPTS_DIR))
        from pine_interp import synthetic_bars, run_file, Platform

        bars = synthetic_bars(bars_count, seed=42)
        platform = Platform(mintick=0.01, timeframe="60")
        res = run_file(temp_path, bars, platform=platform)

        plots_series = {}
        for k, v in res.plots.items():
            plots_series[str(k)] = [None if item is None or (isinstance(item, float) and math.isnan(item)) else item for item in v]

        # Calculate performance metrics
        primary_plot = next(iter(plots_series.values())) if plots_series else [0.0] * len(bars)
        
        equity = 10000.0
        equity_curve = [equity]
        trades = 0
        wins = 0
        gross_profit = 0.0
        gross_loss = 0.0
        peak_equity = equity
        max_dd_pct = 0.0
        returns = []

        for i in range(1, len(bars)):
            cp = bars[i - 1]["close"]
            cc = bars[i]["close"]
            sig = primary_plot[i - 1] if i - 1 < len(primary_plot) else 0
            ret = (cc - cp) / cp
            pnl = ret * equity if sig and (sig is True or (isinstance(sig, (int, float)) and sig > 0)) else 0.0
            
            equity += pnl
            equity_curve.append(round(equity, 2))
            returns.append(pnl / (equity - pnl) if (equity - pnl) > 0 else 0.0)

            if pnl > 0:
                wins += 1
                gross_profit += pnl
                trades += 1
            elif pnl < 0:
                gross_loss += abs(pnl)
                trades += 1

            if equity > peak_equity:
                peak_equity = equity
            dd = (peak_equity - equity) / peak_equity * 100 if peak_equity > 0 else 0
            if dd > max_dd_pct:
                max_dd_pct = dd

        mean_r = sum(returns) / len(returns) if returns else 0.0
        var_r = sum((r - mean_r) ** 2 for r in returns) / len(returns) if returns else 0.0
        std_r = math.sqrt(var_r) if var_r > 0 else 1e-6
        sharpe = round((mean_r / std_r) * math.sqrt(252), 2)
        total_ret = round(((equity - 10000.0) / 10000.0) * 100, 2)
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 1.0)
        win_rate = round((wins / trades * 100), 1) if trades > 0 else 0.0

        return JSONResponse({
            "success": True,
            "bars": bars,
            "plots": plots_series,
            "drawings_count": len(res.drawings),
            "alerts_count": len(res.alerts),
            "metrics": {
                "total_return_pct": total_ret,
                "sharpe_ratio": sharpe,
                "max_drawdown_pct": round(max_dd_pct, 2),
                "profit_factor": profit_factor,
                "win_rate_pct": win_rate,
                "total_trades": trades,
                "final_equity": round(equity, 2),
                "equity_curve": equity_curve
            }
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ---------------------------------------------------------------------------
# Webhook Testing API
# ---------------------------------------------------------------------------
@app.post("/api/webhook/test")
async def test_webhook_api(request: Request):
    data = await request.json()
    payload_str = data.get("payload", "")
    url = data.get("url", "")
    
    import sys
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    from test_webhook import validate_payload, send_mock_webhook

    is_valid, msg, parsed_json = validate_payload(payload_str)
    if not is_valid:
        return JSONResponse({"success": False, "error": msg})

    dispatch_res = None
    if url:
        dispatch_res = send_mock_webhook(url, parsed_json)

    return JSONResponse({
        "success": True,
        "validation": msg,
        "mock_payload": parsed_json,
        "dispatch": dispatch_res
    })


# ---------------------------------------------------------------------------
# Workspace File Management
# ---------------------------------------------------------------------------
@app.get("/api/files/list")
async def list_files():
    tree = []
    for category in ("indicators", "strategies", "libraries"):
        cat_dir = ROOT / category
        if cat_dir.exists():
            cat_node = {"name": category, "is_dir": True, "children": []}
            for p in sorted(cat_dir.glob("**/*.pine")):
                rel = p.relative_to(ROOT)
                cat_node["children"].append({
                    "name": p.name,
                    "path": str(rel).replace("\\", "/"),
                    "is_dir": False
                })
            tree.append(cat_node)
    return JSONResponse({"tree": tree})


@app.post("/api/files/read")
async def read_file_content(request: Request):
    data = await request.json()
    rel_path = data.get("path", "")
    target = (ROOT / rel_path).resolve()
    if not str(target).startswith(str(ROOT)) or not target.exists():
        return JSONResponse({"error": "File not found or forbidden path"}, status_code=404)
    return JSONResponse({"content": target.read_text(encoding="utf-8")})


@app.post("/api/files/write")
async def write_file_content(request: Request):
    data = await request.json()
    rel_path = data.get("path", "")
    content = data.get("content", "")
    target = (ROOT / rel_path).resolve()
    if not str(target).startswith(str(ROOT)):
        return JSONResponse({"error": "Forbidden path"}, status_code=403)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return JSONResponse({"success": True, "path": rel_path})


# Mount frontend static files
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
