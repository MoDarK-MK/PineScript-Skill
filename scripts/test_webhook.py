#!/usr/bin/env python3
"""
test_webhook.py - TradingView Alert JSON Webhook Validator and Mock Dispatcher.

Features:
- Validates JSON format and syntax in TradingView alert messages
- Replaces Pine Script alert placeholders (e.g., {{ticker}}, {{strategy.order.action}}) with realistic mock values
- Simulates sending the webhook to local/remote bot endpoints (e.g. 3Commas, Binance, Bybit, custom webhook)
- Reports HTTP status code, latency, and response headers

Usage:
    python scripts/test_webhook.py --payload '{"symbol": "{{ticker}}", "action": "{{strategy.order.action}}", "qty": {{strategy.order.contracts}}}'
    python scripts/test_webhook.py --file alert_payload.json --url http://localhost:5000/webhook
"""

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, Any, Tuple

# Standard TradingView alert placeholders
PLACEHOLDER_MOCKS = {
    "{{ticker}}": "BTCUSDT",
    "{{exchange}}": "BINANCE",
    "{{close}}": "68500.25",
    "{{open}}": "68200.00",
    "{{high}}": "68900.50",
    "{{low}}": "68100.00",
    "{{volume}}": "1425.8",
    "{{time}}": "2026-08-29T12:00:00Z",
    "{{timenow}}": "1787998800",
    "{{interval}}": "15",
    "{{strategy.order.action}}": "buy",
    "{{strategy.order.contracts}}": "0.15",
    "{{strategy.order.price}}": "68450.00",
    "{{strategy.order.id}}": "LongEntry",
    "{{strategy.order.comment}}": "EMA Trend Breakout",
    "{{strategy.position_size}}": "0.15",
    "{{strategy.market_position}}": "long"
}


def substitute_placeholders(template: str, custom_values: Dict[str, str] = None) -> str:
    values = dict(PLACEHOLDER_MOCKS)
    if custom_values:
        values.update(custom_values)

    result = template
    for ph, mock_val in values.items():
        result = result.replace(ph, mock_val)

    # Check for any remaining untranslated {{ ... }} placeholders
    remaining = re.findall(r'\{\{[a-zA-Z0-9_.]+\}\}', result)
    for ph in remaining:
        # Mock with generic value
        clean_name = ph.strip("{}")
        result = result.replace(ph, f"MOCK_{clean_name.upper()}")

    return result


def validate_payload(raw_template: str) -> Tuple[bool, str, Any]:
    """Validates if the template produces valid JSON after placeholder substitution."""
    substituted = substitute_placeholders(raw_template)
    try:
        parsed = json.loads(substituted)
        return True, "Valid JSON payload", parsed
    except json.JSONDecodeError as e:
        return False, f"JSON Syntax Error: {e.msg} at line {e.lineno}, col {e.colno}", None


def send_mock_webhook(url: str, payload_data: Any, headers: Dict[str, str] = None) -> Dict[str, Any]:
    """Sends HTTP POST request with the JSON payload to the specified webhook URL."""
    headers = headers or {"Content-Type": "application/json", "User-Agent": "TradingView-Webhook-Simulator/1.0"}
    json_bytes = json.dumps(payload_data).encode("utf-8")
    req = urllib.request.Request(url, data=json_bytes, headers=headers, method="POST")

    start_time = time.time()
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            latency_ms = round((time.time() - start_time) * 1000, 2)
            resp_body = response.read().decode("utf-8", errors="replace")
            return {
                "success": True,
                "status_code": response.status,
                "latency_ms": latency_ms,
                "response_body": resp_body
            }
    except urllib.error.HTTPError as e:
        latency_ms = round((time.time() - start_time) * 1000, 2)
        resp_body = e.read().decode("utf-8", errors="replace")
        return {
            "success": False,
            "status_code": e.code,
            "latency_ms": latency_ms,
            "error": f"HTTP Error {e.code}: {e.reason}",
            "response_body": resp_body
        }
    except Exception as e:
        latency_ms = round((time.time() - start_time) * 1000, 2)
        return {
            "success": False,
            "status_code": 0,
            "latency_ms": latency_ms,
            "error": str(e)
        }


def main():
    parser = argparse.ArgumentParser(description="TradingView Alert JSON Webhook Validator and Mock Dispatcher.")
    parser.add_argument("--payload", help="Raw alert JSON template string")
    parser.add_argument("--file", help="Path to JSON alert template file")
    parser.add_argument("--url", help="Webhook destination URL to test dispatch")
    args = parser.parse_args()

    template = ""
    if args.file:
        template = Path(args.file).read_text(encoding="utf-8")
    elif args.payload:
        template = args.payload
    else:
        # Default sample payload
        template = json.dumps({
            "ticker": "{{ticker}}",
            "action": "{{strategy.order.action}}",
            "contracts": "{{strategy.order.contracts}}",
            "price": "{{strategy.order.price}}",
            "timestamp": "{{timenow}}"
        }, indent=2)
        print("No payload provided. Using sample TradingView strategy alert template:")
        print(template)
        print()

    is_valid, msg, parsed_json = validate_payload(template)
    print(f"Validation Result: {'[SUCCESS]' if is_valid else '[FAILED]'} {msg}")

    if is_valid:
        print("\nSubstituted Mock Payload:")
        print(json.dumps(parsed_json, indent=2))

        if args.url:
            print(f"\nDispatching mock webhook to: {args.url} ...")
            res = send_mock_webhook(args.url, parsed_json)
            if res["success"]:
                print(f"Response: HTTP {res['status_code']} ({res['latency_ms']} ms)")
                print(f"Body: {res.get('response_body', '')}")
            else:
                print(f"Dispatch Failed: {res.get('error')} ({res['latency_ms']} ms)")
                if "response_body" in res:
                    print(f"Body: {res['response_body']}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
