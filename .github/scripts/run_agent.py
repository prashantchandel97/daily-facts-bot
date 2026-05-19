#!/usr/bin/env python3
"""
Daily Facts Bot — Agent Runner
Uses the Anthropic Python SDK to run the facts-generator agent.

Usage:
    python3 .github/scripts/run_agent.py facts-generator

Requires:
    ANTHROPIC_API_KEY env var
    BRAVE_API_KEY env var  (enables web search)
"""

import json
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import anthropic
import requests

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent.parent.parent   # repo root
MODEL     = "claude-sonnet-4-6"                   # Sonnet: quality matters for public posts
MAX_TOKENS = 8192
MAX_TURNS  = 30
INTER_TURN_SLEEP = 30   # facts agent reads less data than strategy blog — shorter pauses


# ── Date helpers ──────────────────────────────────────────────────────────────

def today_str() -> str:
    return date.today().isoformat()

def today_month_day() -> str:
    return date.today().strftime("%B %-d")   # e.g. "May 18"


# ── Tool implementations ───────────────────────────────────────────────────────

def tool_read_file(path: str) -> str:
    p = BASE_DIR / path
    if not p.exists():
        return f"ERROR: File not found: {path}"
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        return f"ERROR reading {path}: {e}"


def tool_write_file(path: str, content: str) -> str:
    p = BASE_DIR / path
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(content, encoding="utf-8")
        return f"OK: wrote {len(content)} chars to {path}"
    except Exception as e:
        return f"ERROR writing {path}: {e}"


def tool_list_directory(path: str) -> str:
    p = BASE_DIR / path
    if not p.exists():
        return f"ERROR: Directory not found: {path}"
    try:
        entries = sorted(p.iterdir(), key=lambda x: x.name)
        lines = []
        for e in entries:
            kind = "dir" if e.is_dir() else "file"
            lines.append(f"{kind}  {e.name}")
        return "\n".join(lines) if lines else "(empty directory)"
    except Exception as e:
        return f"ERROR listing {path}: {e}"


def tool_web_search(query: str) -> str:
    """Search the web via Brave Search API."""
    api_key = os.environ.get("BRAVE_API_KEY", "")
    if not api_key:
        return "ERROR: BRAVE_API_KEY not set."
    try:
        resp = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": api_key,
            },
            params={"q": query, "count": 8, "text_decorations": False},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("web", {}).get("results", [])
        if not results:
            return "No results found."
        lines = []
        for r in results:
            lines.append(f"Title: {r.get('title', '')}")
            lines.append(f"URL: {r.get('url', '')}")
            lines.append(f"Snippet: {r.get('description', '')}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR searching: {e}"


def tool_fetch_url(url: str) -> str:
    """Fetch the text content of a URL."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; DailyFactsBot/1.0)"}
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        text = re.sub(r"<[^>]+>", " ", resp.text)
        text = re.sub(r"\s{3,}", "\n\n", text)
        return text[:6000]
    except Exception as e:
        return f"ERROR fetching {url}: {e}"


# ── Tool registry ─────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "read_file",
        "description": "Read the content of a file. Path is relative to repo root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Write (create or overwrite) a file. Path is relative to repo root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "list_directory",
        "description": "List files in a directory, sorted alphabetically.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "web_search",
        "description": "Search the web. Use this to find historical events for today's date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "fetch_url",
        "description": "Fetch the text content of a URL for more detail.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"}
            },
            "required": ["url"]
        }
    },
]


def dispatch_tool(name: str, inputs: dict) -> str:
    if name == "read_file":
        return tool_read_file(inputs["path"])
    elif name == "write_file":
        return tool_write_file(inputs["path"], inputs["content"])
    elif name == "list_directory":
        return tool_list_directory(inputs["path"])
    elif name == "web_search":
        return tool_web_search(inputs["query"])
    elif name == "fetch_url":
        return tool_fetch_url(inputs["url"])
    else:
        return f"ERROR: Unknown tool '{name}'"


# ── Agentic loop ──────────────────────────────────────────────────────────────

def run_agent(agent_type: str) -> None:
    prompt_path = BASE_DIR / ".github" / "prompts" / f"{agent_type}.md"
    if not prompt_path.exists():
        print(f"ERROR: Prompt not found: {prompt_path}", file=sys.stderr)
        sys.exit(1)

    system_prompt = prompt_path.read_text(encoding="utf-8")

    hour = datetime.utcnow().hour
    date_context = (
        f"\n\n---\n"
        f"**Context injected at runtime:**\n"
        f"- Today's date: {today_str()}\n"
        f"- Day of week: {date.today().strftime('%A')}\n"
        f"- Month and day: {today_month_day()}\n"
        f"- Brief file to write: briefs/brief-{today_str()}-{hour:02d}.md\n"
        f"- Post record file to write: posts/daily-{today_str()}-{hour:02d}.md\n"
    )

    system_prompt = system_prompt + date_context

    client = anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        max_retries=6,
    )

    messages = [
        {"role": "user", "content": "Execute your task now. Find today's fact and write the brief."}
    ]

    print(f"\n=== Daily Facts Bot: {agent_type} ===")
    print(f"Today: {today_str()} ({today_month_day()})")
    print(f"Model: {MODEL}")
    print("=" * 50)

    for turn in range(MAX_TURNS):
        print(f"\n[Turn {turn + 1}] Calling Claude API...")

        for attempt in range(6):
            try:
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=system_prompt,
                    tools=TOOLS,
                    messages=messages,
                )
                break
            except anthropic.RateLimitError:
                wait = 65 * (attempt + 1)
                print(f"  [429] Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                if attempt == 5:
                    raise
        else:
            break

        print(f"  stop_reason: {response.stop_reason}")

        assistant_content = response.content
        for block in assistant_content:
            if hasattr(block, "text"):
                preview = block.text[:200].replace("\n", " ")
                print(f"  Text: {preview}...")

        messages.append({"role": "assistant", "content": assistant_content})

        if response.stop_reason == "end_turn":
            print("\n[Done] Agent finished.")
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in assistant_content:
                if block.type == "tool_use":
                    print(f"  Tool: {block.name}({list(block.input.keys())})")
                    result = dispatch_tool(block.name, block.input)
                    print(f"  Result: {result[:120].replace(chr(10), ' ')}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "user", "content": tool_results})
            print(f"  Sleeping {INTER_TURN_SLEEP}s...")
            time.sleep(INTER_TURN_SLEEP)
        else:
            print(f"[WARN] Unexpected stop_reason: {response.stop_reason}")
            break

    else:
        print(f"\n[WARN] Reached max turns ({MAX_TURNS}).")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 run_agent.py <agent-type>")
        sys.exit(1)

    agent_type = sys.argv[1]
    valid = {"facts-generator"}
    if agent_type not in valid:
        print(f"ERROR: Unknown agent '{agent_type}'. Must be one of: {valid}", file=sys.stderr)
        sys.exit(1)

    run_agent(agent_type)
