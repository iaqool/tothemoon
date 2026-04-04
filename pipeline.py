"""
TTM Lead Gen — ЕДИНЫЙ ПАЙПЛАЙН
================================
Запустите один раз: py pipeline.py

Делает всё:
  1. Скрапит новые крипто-проекты из CoinGecko → Supabase
  2. Находит BD/Founder/Listing персоналий через Serper.dev
  3. Выводит итоговый брифинг

После этого — просто работайте в дашборде: http://localhost:5173
"""

import sys
import time
from datetime import datetime


def banner(text: str, char: str = "═"):
    width = 62
    print(f"\n{'=' * width}")
    print(f"  {text}")
    print(f"{'=' * width}\n")


def run_pipeline():
    start = datetime.now()
    banner(f"🚀 TTM LEAD PIPELINE  —  {start.strftime('%d %b %Y, %H:%M')}")

    # ── STEP 1A: SCRAPER ───────────────────────────────────────────────────────
    print("┌─────────────────────────────────────────────────────┐")
    print("│  STEP 1A / 3 —  Scraping new projects (CoinGecko)  │")
    print("└─────────────────────────────────────────────────────┘\n")

    try:
        from scraper import run as scraper_run

        new_projects = scraper_run()
        if new_projects is None:
            new_projects = 0
    except Exception as e:
        print(f"[CRITICAL] Scraper failed: {e}")
        sys.exit(1)

    # ── STEP 1B: UPCOMING SCRAPER ─────────────────────────────────────────────
    print("\n┌─────────────────────────────────────────────────────────────┐")
    print("│  STEP 1B / 3 —  Scraping upcoming token sales (ICO Drops) │")
    print("└─────────────────────────────────────────────────────────────┘\n")

    try:
        from scraper_upcoming import run as scraper_upcoming_run

        upcoming_projects = scraper_upcoming_run(limit=30)
        if upcoming_projects is None:
            upcoming_projects = 0
    except Exception as e:
        print(f"[WARN] Upcoming scraper failed: {e}")
        upcoming_projects = 0

    # ── STEP 2: ENRICHER ───────────────────────────────────────────────────────
    print("\n┌──────────────────────────────────────────────────────────┐")
    print("│  STEP 2 / 3  —  Enriching contacts (BD / Founders / TG) │")
    print("└──────────────────────────────────────────────────────────┘\n")

    try:
        from enricher import run as enricher_run

        # Обогащаем топ-50 по приоритету и MCap (не только новые —
        # некоторые старые могли быть без индивидуальных контактов)
        new_contacts = enricher_run(limit=50)
    except Exception as e:
        print(f"[WARN] Enricher error: {e}")
        new_contacts = 0

    # ── SUMMARY ────────────────────────────────────────────────────────────────
    elapsed = (datetime.now() - start).seconds
    banner(f"✅ PIPELINE COMPLETE  in {elapsed}s")
    print(f"  📦 New projects   : {new_projects}")
    print(f"  🔥 Upcoming leads : {upcoming_projects}")
    print(f"  📇 New contacts   : {new_contacts}")
    print(f"  🌐 Dashboard      : http://localhost:5173")

    time.sleep(1)

    # ── STEP 3: BRIEFING ───────────────────────────────────────────────────────
    print("\n┌──────────────────────────────────────────────────────────┐")
    print("│  STEP 3 / 3  —  Daily Briefing                           │")
    print("└──────────────────────────────────────────────────────────┘")

    try:
        from briefing import run as briefing_run

        briefing_run()
    except Exception as e:
        print(f"[WARN] Briefing error: {e}")

    # ── STEP 4 (Optional): OUTREACH ─────────────────────────────────────────────
    if "--outreach" in sys.argv:
        print("\n┌──────────────────────────────────────────────────────────┐")
        print("│  STEP 4  —  Automated Email Outreach                     │")
        print("└──────────────────────────────────────────────────────────┘")
        try:
            from auto_outreach import run_outreach_cycle

            run_outreach_cycle()
        except Exception as e:
            print(f"[WARN] Outreach error: {e}")


if __name__ == "__main__":
    run_pipeline()
