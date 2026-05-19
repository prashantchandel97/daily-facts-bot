#!/usr/bin/env python3
"""
Daily Facts Brief Sender

Reads today's brief from briefs/brief-YYYY-MM-DD.md and sends it to Telegram.
Runs after the facts-generator agent in the daily-facts.yml workflow.

Usage:
    python3 facts_publisher.py
    python3 facts_publisher.py --dry-run

Requires env vars:
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID
"""

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR   = Path(__file__).parent
BRIEFS_DIR = BASE_DIR / "briefs"
BRIEF_LOG  = BRIEFS_DIR / "brief-log.json"

load_dotenv(BASE_DIR / ".env")


# ── File discovery ────────────────────────────────────────────────────────────

def find_todays_brief() -> Path | None:
    today = date.today().isoformat()
    candidate = BRIEFS_DIR / f"brief-{today}.md"
    if not candidate.exists() or candidate.stat().st_size == 0:
        return None
    content = candidate.read_text().strip()
    if content == "SKIP":
        print("[Skip] Agent found nothing good today.")
        return None
    return candidate


def already_sent(brief_file: Path) -> bool:
    if not BRIEF_LOG.exists():
        return False
    try:
        log = json.loads(BRIEF_LOG.read_text())
        for entry in log:
            if entry.get("brief_file") == brief_file.name and entry.get("sent"):
                print(f"[Skip] Already sent {brief_file.name}")
                return True
    except Exception:
        pass
    return False


# ── Telegram delivery ─────────────────────────────────────────────────────────

def send_telegram(message: str, dry_run: bool = False) -> bool:
    if dry_run:
        print("\n=== DRY RUN — Brief content ===")
        print(message)
        print("=== END DRY RUN ===\n")
        return True

    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        print("[Error] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set", file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    # Split on section dividers if over 4000 chars
    if len(message) <= 4000:
        chunks = [message]
    else:
        parts = message.split("────────────────────────────────────")
        chunks, current = [], ""
        for part in parts:
            if len(current) + len(part) > 3800:
                if current:
                    chunks.append(current)
                current = part
            else:
                current += "────────────────────────────────────" + part if current else part
        if current:
            chunks.append(current)

    all_ok = True
    for i, chunk in enumerate(chunks, 1):
        try:
            resp = requests.post(
                url,
                json={"chat_id": chat_id, "text": chunk.strip()},
                timeout=15,
            )
            if resp.ok:
                print(f"  Sent chunk {i}/{len(chunks)} ({len(chunk)} chars)")
            else:
                print(f"  [Error] {resp.status_code}: {resp.text}", file=sys.stderr)
                all_ok = False
        except Exception as e:
            print(f"  [Error] {e}", file=sys.stderr)
            all_ok = False

    return all_ok


# ── Logging ───────────────────────────────────────────────────────────────────

def write_log(brief_file: Path, sent: bool) -> None:
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    log = []
    if BRIEF_LOG.exists():
        try:
            log = json.loads(BRIEF_LOG.read_text())
        except json.JSONDecodeError:
            log = []

    log.append({
        "timestamp":  datetime.now().isoformat(),
        "brief_file": brief_file.name,
        "sent":       sent,
    })
    BRIEF_LOG.write_text(json.dumps(log, indent=2))
    print(f"[Log] Saved to briefs/brief-log.json")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Send daily facts brief to Telegram")
    parser.add_argument("--dry-run", action="store_true", help="Print without sending")
    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN MODE ===")

    brief_file = find_todays_brief()
    if not brief_file:
        print(f"[Skip] No brief for {date.today().isoformat()}.")
        sys.exit(0)

    print(f"Brief: {brief_file.name} ({brief_file.stat().st_size} bytes)")

    if already_sent(brief_file):
        sys.exit(0)

    message = brief_file.read_text()
    sent = send_telegram(message, dry_run=args.dry_run)
    write_log(brief_file, sent=sent if not args.dry_run else False)

    if sent:
        print("\n[Done] Brief sent.")
    else:
        print("\n[Error] Brief not sent.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
