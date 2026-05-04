"""
Telegram Channel Parser for Tothemoon Lead Gen Pipeline.

Connects to Telegram via Telethon, reads recent posts from configured channels,
classifies them with Gemini AI, and stores relevant signals in Supabase.

Usage:
    python tg_parser.py

Environment variables:
    TELEGRAM_API_ID       - from https://my.telegram.org
    TELEGRAM_API_HASH     - from https://my.telegram.org
    TELEGRAM_SESSION      - StringSession (generated via tg_auth.py)
    SUPABASE_URL          - Supabase project URL
    SUPABASE_KEY          - Supabase anon key
    GEMINI_API_KEY        - Google Gemini API key
    TG_CHANNELS           - comma-separated channel usernames (e.g. "crypto_news,ton_news")
    TG_PARSE_LIMIT        - messages per channel per run (default: 50)
"""

import asyncio
import json
import os
import re
from datetime import datetime, timezone

import google.generativeai as genai
from dotenv import load_dotenv
from supabase import create_client
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID") or "0")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", "")
TG_CHANNELS = [ch.strip() for ch in os.getenv("TG_CHANNELS", "").split(",") if ch.strip()]
TG_PARSE_LIMIT = int(os.getenv("TG_PARSE_LIMIT") or "50")

CLASSIFY_PROMPT = """You are a crypto BD analyst for a CEX listing agency.
Analyze each Telegram post and extract actionable outreach data.

Return JSON with these fields:
1. signal_type: "tge_listing" | "activity" | "long_term" | "noise"
   - tge_listing: TGE announced, token launch, exchange listing, IDO/IEO
   - activity: campaign, partnership, airdrop, testnet, mainnet launch
   - long_term: funding round, growth metrics, ecosystem expansion
   - noise: irrelevant (memes, price talk, generic news)

2. project_name: specific project name (null if generic news)
3. ticker: token ticker (null if not mentioned)
4. chain: blockchain (Solana, TON, Base, Ethereum, BNB Chain, etc; null if unclear)
5. ai_summary: 1 sentence — what happened and why we should contact them
6. relevance_score: 1-10 (10 = must contact now)
7. project_links: object with any links found or inferred:
   - website: project website URL (null if not found)
   - twitter: Twitter/X URL or handle (null if not found)
   - telegram: project Telegram group/channel URL (null if not found)

Priority:
- TGE/listing = 8-10, new projects > established ones
- Extract ALL contact links from the post text (websites, Twitter handles, Telegram links)
- If you see @username in text, include it as twitter or telegram link
- noise = score 1-2

Respond with valid JSON only. Example:
{"signal_type": "tge_listing", "project_name": "SomeToken", "ticker": "SOME", "chain": "Solana", "ai_summary": "SomeToken TGE May 15, Bybit listing confirmed.", "relevance_score": 9, "project_links": {"website": "https://sometoken.io", "twitter": "@SomeToken", "telegram": "https://t.me/sometoken"}}
"""


def classify_post(text: str) -> dict:
    """Use Gemini to classify a single Telegram post."""
    if not text or len(text.strip()) < 20:
        return {
            "signal_type": "noise",
            "project_name": None,
            "ticker": None,
            "chain": None,
            "ai_summary": None,
            "relevance_score": 1,
        }

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.0-flash")

    try:
        response = model.generate_content(
            [CLASSIFY_PROMPT, f"POST:\n{text[:3000]}"],
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                max_output_tokens=500,
            ),
        )

        raw = response.text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

        result = json.loads(raw)
        valid_types = {"tge_listing", "activity", "long_term", "noise"}
        if result.get("signal_type") not in valid_types:
            result["signal_type"] = "noise"
        result["relevance_score"] = max(1, min(10, int(result.get("relevance_score", 1))))
        return result

    except Exception as e:
        print(f"[WARN] Gemini classification failed: {e}")
        return {
            "signal_type": "noise",
            "project_name": None,
            "ticker": None,
            "chain": None,
            "ai_summary": None,
            "relevance_score": 1,
        }


async def parse_channels():
    """Main parsing pipeline: connect to TG, fetch posts, classify, store."""
    if not all([TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION]):
        print("[ERROR] Missing Telegram credentials. Run tg_auth.py first.")
        return

    if not TG_CHANNELS:
        print("[ERROR] No channels configured. Set TG_CHANNELS env var.")
        return

    if not GEMINI_API_KEY:
        print("[ERROR] Missing GEMINI_API_KEY.")
        return

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Get existing message IDs to avoid reprocessing (scoped to configured channels)
    existing_keys = set()
    for ch in TG_CHANNELS:
        res = supabase.table("tg_signals").select("channel_username, message_id").eq("channel_username", ch).order("message_id", desc=True).limit(5000).execute()
        for row in (res.data or []):
            existing_keys.add((row["channel_username"], row["message_id"]))
    print(f"[INFO] {len(existing_keys)} existing signals in database")

    client = TelegramClient(StringSession(TELEGRAM_SESSION), TELEGRAM_API_ID, TELEGRAM_API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        print("[ERROR] Telegram session is invalid or expired. Re-run tg_auth.py.")
        await client.disconnect()
        return

    total_new = 0
    total_relevant = 0

    try:
        for channel_username in TG_CHANNELS:
            print(f"\n[PARSE] Channel: @{channel_username}")
            try:
                entity = await client.get_entity(channel_username)
                channel_title = getattr(entity, "title", channel_username)
            except Exception as e:
                print(f"[ERROR] Could not resolve @{channel_username}: {e}")
                continue

            try:
                messages = await client.get_messages(entity, limit=TG_PARSE_LIMIT)
            except Exception as e:
                print(f"[ERROR] Could not fetch messages from @{channel_username}: {e}")
                continue

            new_signals = []
            for msg in messages:
                if not msg.text or len(msg.text.strip()) < 20:
                    continue

                if (channel_username, msg.id) in existing_keys:
                    continue

                classification = await asyncio.to_thread(classify_post, msg.text)

                msg_date = msg.date
                if msg_date and msg_date.tzinfo is None:
                    msg_date = msg_date.replace(tzinfo=timezone.utc)

                links = classification.get("project_links") or {}

                signal = {
                    "channel_username": channel_username,
                    "channel_title": channel_title,
                    "message_id": msg.id,
                    "message_text": msg.text[:5000],
                    "signal_type": classification["signal_type"],
                    "ai_summary": classification.get("ai_summary"),
                    "project_name": classification.get("project_name"),
                    "ticker": classification.get("ticker"),
                    "chain": classification.get("chain"),
                    "relevance_score": classification["relevance_score"],
                    "message_date": msg_date.isoformat() if msg_date else None,
                    "project_links": links if links else None,
                }
                new_signals.append(signal)

            if new_signals:
                for signal in new_signals:
                    try:
                        supabase.table("tg_signals").upsert(
                            signal, on_conflict="channel_username,message_id"
                        ).execute()
                    except Exception as e:
                        print(f"[WARN] Failed to insert signal: {e}")

                relevant = [s for s in new_signals if s["signal_type"] != "noise"]
                total_new += len(new_signals)
                total_relevant += len(relevant)
                print(f"  -> {len(new_signals)} new signals ({len(relevant)} relevant)")
            else:
                print("  -> No new signals")
    finally:
        await client.disconnect()

    print(f"\n[DONE] Total: {total_new} new signals, {total_relevant} relevant")
    return total_new, total_relevant


def main():
    asyncio.run(parse_channels())


if __name__ == "__main__":
    main()
