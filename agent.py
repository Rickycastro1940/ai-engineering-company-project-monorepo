from __future__ import annotations

import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
CONVERSATION_LOG = Path("conversation_log.csv")
LOG_HEADERS = ["timestamp", "session_id", "role", "message"]

SYSTEM_PROMPT = """You are an inventory management assistant for a restaurant company.
You help staff check stock, add products, update quantities, and review low-stock alerts.
Use the available tools to read and update inventory through the company API.
Answer clearly and concisely after you have the data you need."""

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_inventory",
            "description": "Return the full list of products currently in inventory.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_product",
            "description": "Add a new product to inventory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Product name"},
                    "quantity": {"type": "integer", "description": "Initial stock quantity", "minimum": 0},
                    "unit": {"type": "string", "description": "Unit of measure, e.g. kg, boxes, liters"},
                },
                "required": ["name", "quantity", "unit"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_stock",
            "description": "Update stock for a product by applying a delta. Positive delta adds stock; negative delta removes stock.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "ID of the product to update"},
                    "delta": {"type": "integer", "description": "Amount to add (positive) or remove (negative)"},
                },
                "required": ["product_id", "delta"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_low_stock_alerts",
            "description": "Return products whose quantity is below the configured threshold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "threshold": {
                        "type": "integer",
                        "description": "Alert when quantity is below this value",
                        "default": 10,
                        "minimum": 0,
                    }
                },
                "additionalProperties": False,
            },
        },
    },
]


def append_conversation(session_id: str, role: str, message: str) -> None:
    file_exists = CONVERSATION_LOG.exists() and CONVERSATION_LOG.stat().st_size > 0
    with CONVERSATION_LOG.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "session_id": session_id,
                "role": role,
                "message": message,
            }
        )


def _api_request(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"{API_BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8")
        try:
            parsed = json.loads(detail)
        except json.JSONDecodeError:
            parsed = {"detail": detail or error.reason}
        return {"error": True, "status_code": error.code, "detail": parsed}
    except urllib.error.URLError as error:
        return {
            "error": True,
            "status_code": 0,
            "detail": f"Could not reach API at {API_BASE_URL}: {error}",
        }


def execute_tool(name: str, arguments: dict[str, Any]) -> Any:
    if name == "list_inventory":
        return _api_request("GET", "/inventory")
    if name == "add_product":
        return _api_request("POST", "/inventory", arguments)
    if name == "update_stock":
        product_id = arguments["product_id"]
        return _api_request("PATCH", f"/inventory/{product_id}", {"delta": arguments["delta"]})
    if name == "get_low_stock_alerts":
        threshold = arguments.get("threshold", 10)
        query = urllib.parse.urlencode({"threshold": threshold})
        return _api_request("GET", f"/inventory/alerts?{query}")
    return {"error": True, "detail": f"Unknown tool: {name}"}


def _assistant_message_payload(message: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": "assistant",
        "content": message.content or "",
    }
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            }
            for tool_call in message.tool_calls
        ]
    return payload


def run_agent_turn(client: OpenAI, messages: list[dict[str, Any]], session_id: str) -> str:
    while True:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        message = response.choices[0].message
        messages.append(_assistant_message_payload(message))

        if not message.tool_calls:
            final_response = message.content or ""
            append_conversation(session_id, "assistant", final_response)
            return final_response

        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            try:
                tool_args = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                tool_args = {}

            append_conversation(
                session_id,
                "tool_call",
                json.dumps({"name": tool_name, "arguments": tool_args}),
            )
            tool_result = execute_tool(tool_name, tool_args)
            tool_content = json.dumps(tool_result)
            append_conversation(session_id, "tool", tool_content)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_content,
                }
            )


def check_api_available() -> bool:
    try:
        urllib.request.urlopen(f"{API_BASE_URL}/inventory", timeout=3)
        return True
    except urllib.error.URLError:
        return False


def main() -> int:
    if not GROQ_API_KEY or GROQ_API_KEY == "your_key_here":
        print("Set GROQ_API_KEY in .env before running the agent.", file=sys.stderr)
        return 1

    if not check_api_available():
        print(
            "Could not reach the API. Start it first with: uvicorn api.app:app --reload",
            file=sys.stderr,
        )
        return 1

    session_id = str(uuid.uuid4())
    client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    print(f"Inventory Agent (session {session_id})")
    print(f"API: {API_BASE_URL} | Model: {GROQ_MODEL}")
    print("Type your message and press Enter. Type 'exit' or 'quit' to end.\n")
    append_conversation(session_id, "system", f"Started inventory agent session at {API_BASE_URL}")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            print("Goodbye.")
            append_conversation(session_id, "system", "Session ended by user")
            break

        messages.append({"role": "user", "content": user_input})
        append_conversation(session_id, "user", user_input)

        try:
            response = run_agent_turn(client, messages, session_id)
        except Exception as error:
            print(f"Agent error: {error}", file=sys.stderr)
            append_conversation(session_id, "system", f"Agent error: {error}")
            continue

        print(f"Agent: {response}\n")

    print(f"Conversation appended to {CONVERSATION_LOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
