#!/usr/bin/env python3
"""
Daily Facts Publisher

Reads the current-hour brief, posts tweet option A to X, then sends the brief to Telegram.
Runs after the facts-generator agent in the daily-facts.yml workflow.

Usage:
    python3 facts_publisher.py
    python3 facts_publisher.py --dry-run

Requires env vars:
    X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR   = Path(__file__).parent
BRIEFS_DIR = BASE_DIR / "briefs"
POSTS_DIR  = BASE_DIR / "posts"
BRIEF_LOG  = BRIEFS_DIR / "brief-log.json"

load_dotenv(BASE_DIR / ".env")


# ── File discovery ────────────────────────────────────────────────────────────

def find_todays_brief() -> Path | None:
    today = date.today().isoformat()
    hour  = datetime.utcnow().hour
    candidate = BRIEFS_DIR / f"brief-{today}-{hour:02d}.md"
    if not candidate.exists() or candidate.stat().st_size == 0:
        return None
    content = candidate.read_text().strip()
    if content == "SKIP":
        print("[Skip] Agent found nothing good today.")
        return None
    return candidate


def find_todays_post_record() -> Path | None:
    today = date.today().isoformat()
    hour  = datetime.utcnow().hour
    candidate = POSTS_DIR / f"daily-{today}-{hour:02d}.md"
    if not candidate.exists() or candidate.stat().st_size == 0:
        return None
    return candidate


def brief_to_post_record(brief_file: Path) -> Path:
    name = brief_file.stem.replace("brief-", "daily-")
    return POSTS_DIR / f"{name}.md"


def build_telegram_from_post_record(post_record: Path) -> str:
    fm    = parse_frontmatter(post_record)
    tweet = fm.get("tweet_option_a", "").strip()
    d     = fm.get("date", date.today().isoformat())
    try:
        day_label = datetime.strptime(d, "%Y-%m-%d").strftime("%A, %B %-d")
    except Exception:
        day_label = d
    lines = [
        f"DAILY FACTS | {day_label}",
        "",
        tweet,
        "",
        f"Domain: {fm.get('domain', '—')}  |  Year: {fm.get('year_of_event', '—')}",
        f"Source: {fm.get('source', '—')}",
    ]
    return "\n".join(lines)


def parse_frontmatter(post_file: Path) -> dict:
    if not post_file.exists():
        return {}
    text  = post_file.read_text()
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    fm = {}
    for line in match.group(1).splitlines():
        if ": " in line:
            key, _, val = line.partition(": ")
            val = val.strip()
            if len(val) >= 2 and val[0] in ('"', "'") and val[0] == val[-1]:
                val = val[1:-1]
            fm[key.strip()] = val
    return fm


def already_processed(anchor: Path) -> bool:
    if not BRIEF_LOG.exists():
        return False
    try:
        log = json.loads(BRIEF_LOG.read_text())
        for entry in log:
            if entry.get("brief_file") == anchor.name and entry.get("posted_to_x"):
                print(f"[Skip] Already posted {anchor.name}")
                return True
    except Exception:
        pass
    return False


# ── X posting ─────────────────────────────────────────────────────────────────

def post_to_x(tweet_text: str, dry_run: bool = False) -> bool:
    if dry_run:
        print(f"\n=== DRY RUN — Would post to X ===\n{tweet_text}\n({len(tweet_text)} chars)\n=== END ===\n")
        return True

    api_key    = os.environ.get("X_API_KEY", "")
    api_secret = os.environ.get("X_API_SECRET", "")
    acc_token  = os.environ.get("X_ACCESS_TOKEN", "")
    acc_secret = os.environ.get("X_ACCESS_TOKEN_SECRET", "")

    if not all([api_key, api_secret, acc_token, acc_secret]):
        print("[Error] X API credentials not set — skipping X post.", file=sys.stderr)
        return False

    try:
        from requests_oauthlib import OAuth1Session
    except ImportError:
        print("[Error] requests-oauthlib not installed", file=sys.stderr)
        return False

    print(f"  api_key prefix: {api_key[:6]}... acc_token prefix: {acc_token[:10]}...")
    try:
        oauth = OAuth1Session(api_key, api_secret, acc_token, acc_secret)
        resp  = oauth.post(
            "https://api.twitter.com/2/tweets",
            json={"text": tweet_text},
        )
        print(f"  Status: {resp.status_code}  Body: {resp.text[:200]}")
        if resp.status_code == 201:
            tweet_id = resp.json().get("data", {}).get("id", "?")
            print(f"  Posted to X: tweet_id={tweet_id}")
            return True
        else:
            print(f"  [Error] {resp.status_code}: {resp.text}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"  [Error] X post failed: {type(e).__name__}: {e}", file=sys.stderr)
        return False


# ── Telegram delivery ─────────────────────────────────────────────────────────

def send_telegram(message: str, dry_run: bool = False) -> bool:
    if dry_run:
        print("\n=== DRY RUN — Telegram brief ===")
        print(message)
        print("=== END DRY RUN ===\n")
        return True

    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        print("[Error] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set", file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"

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
                print(f"  Sent Telegram chunk {i}/{len(chunks)} ({len(chunk)} chars)")
            else:
                print(f"  [Error] Telegram {resp.status_code}: {resp.text}", file=sys.stderr)
                all_ok = False
        except Exception as e:
            print(f"  [Error] Telegram: {e}", file=sys.stderr)
            all_ok = False

    return all_ok


# ── Logging ───────────────────────────────────────────────────────────────────

def write_log(brief_file: Path, sent_telegram: bool, posted_to_x: bool) -> None:
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    log = []
    if BRIEF_LOG.exists():
        try:
            log = json.loads(BRIEF_LOG.read_text())
        except json.JSONDecodeError:
            log = []
    log.append({
        "timestamp":   datetime.now().isoformat(),
        "brief_file":  brief_file.name,
        "sent":        sent_telegram,
        "posted_to_x": posted_to_x,
    })
    BRIEF_LOG.write_text(json.dumps(log, indent=2))
    print("[Log] Saved to briefs/brief-log.json")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Post daily fact to X and send Telegram brief")
    parser.add_argument("--dry-run", action="store_true", help="Print without posting or sending")
    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN MODE ===")

    # Support two modes: brief file (daily agent) or post record only (batch generator)
    brief_file  = find_todays_brief()
    post_record = brief_to_post_record(brief_file) if brief_file else find_todays_post_record()

    if not post_record:
        hour = datetime.utcnow().hour
        print(f"[Skip] No content for {date.today().isoformat()} slot {hour:02d}.")
        sys.exit(0)

    anchor = brief_file or post_record
    print(f"Content: {anchor.name} ({anchor.stat().st_size} bytes)")

    if already_processed(anchor):
        sys.exit(0)

    # Extract tweet
    fm         = parse_frontmatter(post_record)
    tweet_text = fm.get("tweet_option_a", "").strip()

    # Post to X
    posted_x = False
    if tweet_text:
        print(f"\nPosting to X ({len(tweet_text)} chars):\n  {tweet_text[:120]}")
        posted_x = post_to_x(tweet_text, dry_run=args.dry_run)
    else:
        print("[Warn] tweet_option_a not found — skipping X post.", file=sys.stderr)

    # Build Telegram message
    if brief_file:
        brief_text = brief_file.read_text()
        if not args.dry_run:
            suffix = "\n\nPosted to X: option A" if posted_x else ("\n\nX post failed — check logs" if tweet_text else "")
            brief_text = brief_text.rstrip() + suffix
    else:
        brief_text = build_telegram_from_post_record(post_record)
        if not args.dry_run and posted_x:
            brief_text += "\n\nPosted to X."
        elif not args.dry_run and tweet_text:
            brief_text += "\n\nX post failed — check logs."

    sent_telegram = send_telegram(brief_text, dry_run=args.dry_run)

    if not args.dry_run:
        write_log(anchor, sent_telegram=sent_telegram, posted_to_x=posted_x)

    if posted_x or sent_telegram:
        print("\n[Done]")
    else:
        print("\n[Error] Both X post and Telegram failed.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
