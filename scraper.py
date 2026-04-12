"""
TTM Lead Gen — CoinGecko API Scraper
Собирает новые крипто-проекты через официальный API,
фильтрует по MCap и сети, сохраняет в Supabase.
"""

import os
import time
import json
import requests
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# ─── Supabase ───────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Задай SUPABASE_URL и SUPABASE_KEY в .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ─── CoinGecko API ──────────────────────────────────────────────────────────
CG_BASE = "https://api.coingecko.com/api/v3"
CG_API_KEY = os.getenv("CG_API_KEY", "")  # Оставь пустым для Demo API
HEADERS = {"x-cg-demo-api-key": CG_API_KEY} if CG_API_KEY else {}

# ─── Фильтры ────────────────────────────────────────────────────────────────
MIN_MCAP = 100_000  # $100k

# Маппинг platform_id → отображаемое название
CHAIN_MAP = {
    "solana": "Solana",
    "the-open-network": "TON",
    "base": "Base",
    "ethereum": "Ethereum",
    "binance-smart-chain": "BNB Chain",
    "tron": "Tron",
    "arbitrum-one": "Arbitrum",
    "polygon-pos": "Polygon",
    "celo": "Celo",
    "stellar": "Stellar",
    "optimistic-ethereum": "Optimism",
    "injective-protocol": "Injective",
}
SUPPORTED_CHAINS = set(CHAIN_MAP.values())
PRIORITY_CHAINS = {"Solana", "TON", "Base"}

# Файл кэша — список id монет, которые мы уже видели
SEEN_FILE = "seen_coins.json"


# ─── Helpers ────────────────────────────────────────────────────────────────
def load_seen() -> set:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


def cg_get(endpoint: str, params: dict = None) -> dict | list | None:
    """Запрос к CoinGecko API с обработкой rate-limit (429)."""
    url = f"{CG_BASE}{endpoint}"
    for attempt in range(5):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=20)
            if r.status_code == 429:
                retry_after = int(r.headers.get("Retry-After", 60))
                print(f"    [RATE LIMIT] Ждём {retry_after}с...")
                time.sleep(retry_after)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            wait = 2**attempt
            print(f"    [ERR] {e} — повтор через {wait}с")
            time.sleep(wait)
    return None


def get_all_coin_list() -> list[dict]:
    """
    /coins/list?include_platform=true
    Возвращает [{id, symbol, name, platforms: {platform_id: contract}}]
    """
    print("[API] Загружаем полный список монет (coins/list)...")
    data = cg_get("/coins/list", {"include_platform": "true"})
    return data or []


def get_markets_batch(coin_ids: list[str]) -> list[dict]:
    """
    /coins/markets — до 250 монет за запрос
    Возвращает market_cap, current_price и т.д.
    """
    ids_str = ",".join(coin_ids[:250])
    data = cg_get(
        "/coins/markets",
        {
            "vs_currency": "usd",
            "ids": ids_str,
            "order": "market_cap_desc",
            "per_page": 250,
            "page": 1,
            "sparkline": "false",
            "locale": "en",
        },
    )
    return data or []


def resolve_chain(platforms: dict) -> tuple[str | None, bool]:
    """Возвращает (chain_name, is_priority) по словарю platforms монеты."""
    # Сначала смотрим приоритетные сети
    for pid, name in CHAIN_MAP.items():
        if pid in platforms and name in PRIORITY_CHAINS:
            return name, True
    # Потом поддерживаемые
    for pid, name in CHAIN_MAP.items():
        if pid in platforms:
            return name, False
    return None, False


def get_coin_links(coin_id: str) -> dict:
    """
    /coins/{id} — получаем links: homepage, twitter, telegram
    Используем только для монет, которые прошли фильтры MCap+Chain.
    """
    data = cg_get(
        f"/coins/{coin_id}",
        {
            "localization": "false",
            "tickers": "false",
            "market_data": "false",
            "community_data": "false",
            "developer_data": "false",
        },
    )
    if not data:
        return {}

    links = data.get("links", {})
    homepage = next((u for u in links.get("homepage", []) if u), None)
    twitter = links.get("twitter_screen_name")
    telegram = links.get("telegram_channel_identifier")

    return {
        "website": homepage,
        "twitter": f"https://x.com/{twitter}" if twitter else None,
        "telegram": f"https://t.me/{telegram}" if telegram else None,
    }


def save_contacts(project_id: str, links: dict, coingecko_url: str):
    rows = []
    if coingecko_url:
        rows.append(
            {
                "project_id": project_id,
                "platform": "CoinGecko",
                "value": coingecko_url,
                "role": "Listing",
            }
        )
    if links.get("website"):
        rows.append(
            {
                "project_id": project_id,
                "platform": "Website",
                "value": links["website"],
                "role": "Official",
            }
        )
    if links.get("twitter"):
        rows.append(
            {
                "project_id": project_id,
                "platform": "X / Twitter",
                "value": links["twitter"],
                "role": "Social",
            }
        )
    if links.get("telegram"):
        rows.append(
            {
                "project_id": project_id,
                "platform": "Telegram",
                "value": links["telegram"],
                "role": "Community",
            }
        )

    if not rows:
        return

    # Попытка batch insert
    try:
        supabase.table("contacts").insert(rows).execute()
    except Exception as e:
        err = str(e).lower()
        # Если batch insert упал из-за дубликатов, делаем поштучную вставку
        if "duplicate" in err or "unique" in err:
            for row in rows:
                try:
                    supabase.table("contacts").insert(row).execute()
                except Exception as e2:
                    if (
                        "duplicate" not in str(e2).lower()
                        and "unique" not in str(e2).lower()
                    ):
                        print(f"    [WARN contacts] {row['platform']}: {e2}")
        else:
            print(f"    [ERROR batch insert contacts] {e}")


# ─── Main ────────────────────────────────────────────────────────────────────
def run():
    print(f"\n{'=' * 60}")
    print(f"  TTM Lead Gen — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}\n")

    seen = load_seen()

    # 1. Полный список монет с платформами
    all_coins = get_all_coin_list()
    print(f"[INFO] Всего монет в CoinGecko: {len(all_coins)}")

    # 2. Отбираем только НОВЫЕ (ещё не виденные) монеты с нужной сетью
    candidates = []
    for coin in all_coins:
        cid = coin["id"]
        if cid in seen:
            continue
        platforms = coin.get("platforms") or {}
        chain, priority = resolve_chain(platforms)
        if chain:
            candidates.append(
                {
                    "id": cid,
                    "name": coin.get("name", "Unknown"),
                    "ticker": coin.get("symbol", "").upper(),
                    "chain": chain,
                    "priority": priority,
                    "platforms": platforms,
                }
            )

    print(f"[INFO] Новых монет с поддерживаемой сетью: {len(candidates)}\n")

    if not candidates:
        print("[INFO] Новых проектов нет. Запустите позже.")
        save_seen(seen)
        return 0

    # 3. Запрашиваем Market Cap батчами по 250
    saved_count = 0
    candidate_ids = [c["id"] for c in candidates]
    markets_map: dict[str, float] = {}

    for i in range(0, len(candidate_ids), 250):
        batch_ids = candidate_ids[i : i + 250]
        print(f"[API] Запрос markets ({i + 1}–{i + len(batch_ids)})...")
        markets = get_markets_batch(batch_ids)
        for m in markets:
            markets_map[m["id"]] = m.get("market_cap") or 0.0
        time.sleep(1.5)  # уважаем rate-limit

    # 4. Фильтрация по MCap и сохранение
    print(f"\n[INFO] Фильтрую и сохраняю...\n")
    for coin in candidates:
        cid = coin["id"]
        name = coin["name"]
        ticker = coin["ticker"]
        chain = coin["chain"]
        priority = coin["priority"]
        mcap = markets_map.get(cid, 0.0)

        # Помечаем как «видели» в любом случае
        seen.add(cid)

        if mcap < MIN_MCAP:
            print(f"  [SKIP] {name} ({ticker}) — MCap ${mcap:,.0f} < $100k")
            continue

        coingecko_url = f"https://www.coingecko.com/en/coins/{cid}"

        # Получаем ссылки только для монет, прошедших фильтр
        time.sleep(1.2)
        links = get_coin_links(cid)

        project_data = {
            "name": name,
            "ticker": ticker,
            "website": coingecko_url,
            "mcap": mcap,
            "chain": chain,
            "source": "CoinGecko",
            "status": "not_contacted",
            "is_priority": priority,
        }

        try:
            res = supabase.table("projects").insert(project_data).execute()
            project_id = res.data[0]["id"] if res.data else None
            saved_count += 1
            flag = "🔥 PRIORITY" if priority else "  OK"
            print(f"  [{flag}] {name} ({ticker}) | {chain} | ${mcap:,.0f}")

            if project_id:
                save_contacts(project_id, links, coingecko_url)

        except Exception as e:
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                print(f"  [EXISTS] {name} уже в базе.")
            else:
                print(f"  [ERROR] {name}: {e}")

    # 5. Сохраняем кэш просмотренных монет
    save_seen(seen)

    print(f"\n{'=' * 60}")
    print(f"  Готово! Новых проектов добавлено: {saved_count}")
    print(f"{'=' * 60}\n")
    return saved_count


if __name__ == "__main__":
    run()
