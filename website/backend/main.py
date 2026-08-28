import os
import subprocess
import tempfile
import json
import urllib.request
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn

app = FastAPI(title="PineScript-Skill App")

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = ROOT / "scripts"
SKILL_PATH = ROOT / "SKILL.md"

def read_skill():
    if not SKILL_PATH.exists():
        return "You are an AI assistant for TradingView Pine Script."
    return SKILL_PATH.read_text(encoding="utf-8")

@app.post("/api/lint")
async def lint_code(request: Request):
    data = await request.json()
    code = data.get("code", "")
    
    # Write code to a temp file
    with tempfile.NamedTemporaryFile(suffix=".pine", delete=False, mode="w", encoding="utf-8") as f:
        f.write(code)
        temp_path = f.name
        
    try:
        # Run pine_lint.py on the temp file
        lint_cmd = ["python", str(SCRIPTS_DIR / "pine_lint.py"), temp_path, "--json"]
        result = subprocess.run(lint_cmd, capture_output=True, text=True, encoding="utf-8")
        
        # The output might have the findings as JSON
        try:
            output_json = json.loads(result.stdout)
            return JSONResponse(output_json)
        except json.JSONDecodeError:
            return JSONResponse({"error": "Failed to parse linter output", "raw": result.stdout, "stderr": result.stderr})
            
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.post("/api/chat")
async def chat(request: Request):
    data = await request.json()
    prompt = data.get("prompt", "")
    model = data.get("model", "llama3.1")
    host = data.get("host", "http://localhost:11434")
    
    url = f"{host}/api/chat"
    system_prompt = read_skill()
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "stream": True
    }
    
    def generate():
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req) as response:
                for line in response:
                    if line:
                        chunk = json.loads(line)
                        if "message" in chunk and "content" in chunk["message"]:
                            yield chunk["message"]["content"]
                        if chunk.get("done"):
                            break
        except Exception as e:
            yield f"Error: Could not connect to Ollama at {host}. Is it running? Details: {str(e)}"
            
    return StreamingResponse(generate(), media_type="text/plain")

# Mount frontend files at the root
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
