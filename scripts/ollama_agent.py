#!/usr/bin/env python3
"""
ollama_agent.py - Query a local Ollama model using the PineScript-Skill.

This script acts as a bridge to use this repository's SKILL.md rules 
with any local LLM running via Ollama. It sends the skill instructions 
as the system prompt and streams the response back to your terminal.

Usage:
    python3 scripts/ollama_agent.py "Write me an RSI indicator"
    python3 scripts/ollama_agent.py "Build a trend strategy" --model codellama
"""
import argparse
import json
import urllib.request
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def read_skill():
    skill_path = ROOT / "SKILL.md"
    if not skill_path.exists():
        print(f"Error: {skill_path} not found.", file=sys.stderr)
        sys.exit(1)
    return skill_path.read_text(encoding="utf-8")

def stream_ollama(prompt, model="llama3.1", host="http://localhost:11434"):
    url = f"{host}/api/chat"
    
    system_prompt = read_skill()
    
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "stream": True
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    print(f"Sending request to Ollama ({model}) at {host}...\n")
    try:
        with urllib.request.urlopen(req) as response:
            for line in response:
                if line:
                    chunk = json.loads(line)
                    if "message" in chunk and "content" in chunk["message"]:
                        print(chunk["message"]["content"], end="", flush=True)
                    if chunk.get("done"):
                        break
        print("\n")
    except Exception as e:
        print(f"\nError communicating with Ollama: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query a local Ollama model using the PineScript-Skill.")
    parser.add_argument("prompt", type=str, help="The prompt/request for the model (e.g. 'Write an RSI strategy')")
    parser.add_argument("--model", type=str, default="llama3.1", help="Ollama model to use (default: llama3.1)")
    parser.add_argument("--host", type=str, default="http://localhost:11434", help="Ollama host URL (default: http://localhost:11434)")
    args = parser.parse_args()
    
    stream_ollama(args.prompt, args.model, args.host)
