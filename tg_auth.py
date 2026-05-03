"""
One-time Telegram authentication script.

Run this locally to generate a StringSession for use in GitHub Actions.
The session string is safe to store as a secret — it does not contain your password.

Usage:
    pip install telethon
    python tg_auth.py

After authentication, copy the printed session string and save it as:
    - GitHub repo secret: TELEGRAM_SESSION
    - Or in your .env file: TELEGRAM_SESSION=<string>

Requirements:
    - TELEGRAM_API_ID and TELEGRAM_API_HASH from https://my.telegram.org
    - Your phone number registered with Telegram
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()


async def main():
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        print("Install telethon first: pip install telethon")
        sys.exit(1)

    api_id = os.getenv("TELEGRAM_API_ID") or input("Enter TELEGRAM_API_ID: ")
    api_hash = os.getenv("TELEGRAM_API_HASH") or input("Enter TELEGRAM_API_HASH: ")

    api_id = int(api_id)

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        phone = input("Enter your phone number (with country code, e.g. +79001234567): ")
        await client.send_code_request(phone)
        code = input("Enter the code you received: ")

        try:
            await client.sign_in(phone, code)
        except Exception:
            password = input("Two-factor authentication enabled. Enter your password: ")
            await client.sign_in(password=password)

    session_string = client.session.save()
    await client.disconnect()

    print("\n" + "=" * 60)
    print("SUCCESS! Your Telegram session string:")
    print("=" * 60)
    print(session_string)
    print("=" * 60)
    print("\nSave this as GitHub secret: TELEGRAM_SESSION")
    print("Or add to .env: TELEGRAM_SESSION=" + session_string[:20] + "...")


if __name__ == "__main__":
    asyncio.run(main())
