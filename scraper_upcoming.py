"""
TTM Lead Gen — Upcoming Token Sales Scraper
Pulls upcoming projects from ICO Drops and saves them to Supabase before they hit CoinGecko.
"""

import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Set SUPABASE_URL and SUPABASE_KEY in .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

BASE_URL = "https://icodrops.com"
UPCOMING_URL = f"{BASE_URL}/category/upcoming-ico/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TTMUpcomingBot/1.0)",
    "Accept-Language": "en-US,en;q=0.9",
}

CHAIN_MAP = {
    "solana": "Solana",
    "base": "Base",
    "ethereum": "Ethereum",
    "arbitrum": "Arbitrum",
    "ton": "TON",
    "bnb": "BNB Chain",
    "binance": "BNB Chain",
    "polygon": "Polygon",
    "optimism": "Optimism",
    "injective": "Injective",
    "stellar": "Stellar",
    "tron": "Tron",
    "celo": "Celo",
}
PRIORITY_CHAINS = {"Solana", "TON", "Base"}
MONEY_RE = re.compile(r"\$?\s*([0-9]+(?:\.[0-9]+)?)\s*([KMB])?", re.IGNORECASE)


def has_project_column(column: str) -> bool:
    try:
        supabase.table("projects").select(f"id, {column}").limit(1).execute()
        return True
    except Exception:
        return False


PROJECT_OPTIONAL_COLUMNS = {
    "is_upcoming": has_project_column("is_upcoming"),
    "launch_date": has_project_column("launch_date"),
    "launchpad": has_project_column("launchpad"),
}


def fetch_soup(url: str) -> BeautifulSoup:
    response = requests.get(url, headers=HEADERS, timeout=25)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def parse_money(text: str) -> float:
    if not text:
        return 0.0
    match = MONEY_RE.search(text.replace(",", ""))
    if not match:
        return 0.0
    value = float(match.group(1))
    suffix = (match.group(2) or "").upper()
    if suffix == "B":
        value *= 1_000_000_000
    elif suffix == "M":
        value *= 1_000_000
    elif suffix == "K":
        value *= 1_000
    return value


def normalize_chain(raw: str) -> str | None:
    if not raw:
        return None
    lower = raw.strip().lower()
    for key, value in CHAIN_MAP.items():
        if key in lower:
            return value
    return raw.strip()


def parse_launch_date(text: str) -> str | None:
    cleaned = (text or "").strip()
    if not cleaned or cleaned.lower() == "upcoming":
        return None

    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            dt = datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            pass

    quarter = re.match(r"Q([1-4]),\s*(\d{4})", cleaned, re.IGNORECASE)
    if quarter:
        month = {"1": 1, "2": 4, "3": 7, "4": 10}[quarter.group(1)]
        dt = datetime(int(quarter.group(2)), month, 1, tzinfo=timezone.utc)
        return dt.isoformat()

    return None


def extract_detail_links(project_url: str) -> dict:
    try:
        soup = fetch_soup(project_url)
    except Exception as exc:
        print(f"    [WARN detail] {project_url}: {exc}")
        return {}

    links = {
        "website": None,
        "twitter": None,
        "telegram": None,
        "launchpad": None,
    }

    header = soup.select_one(".Project-Page-Header__links-box")
    if header:
        for anchor in header.select("a[href]"):
            label = anchor.get_text(" ", strip=True).lower()
            href = anchor.get("href", "").strip()
            if not href:
                continue
            if label == "website" and not links["website"]:
                links["website"] = href
            elif label == "twitter" and not links["twitter"]:
                links["twitter"] = href.replace("twitter.com", "x.com")
            elif label == "telegram" and not links["telegram"]:
                links["telegram"] = href

    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        text = anchor.get_text(" ", strip=True).lower()
        href_lower = href.lower()

        if not links["telegram"] and ("t.me/" in href_lower or "telegram" in text):
            links["telegram"] = href

        if (
            not links["launchpad"]
            and href.startswith("http")
            and (
                any(
                    token in text
                    for token in ("presale", "launchpad", "ido", "ieo", "token sale")
                )
                or any(
                    token in href_lower
                    for token in ("presale", "launchpad", "sale", "ido", "ieo")
                )
            )
        ):
            domain = urlparse(href).netloc.lower()
            if "icodrops.com" not in domain and "dropstab.com" not in domain:
                links["launchpad"] = href

    return links


def save_contacts(project_id: str, project_url: str, links: dict):
    rows = [
        {
            "project_id": project_id,
            "platform": "ICO Drops",
            "value": project_url,
            "role": "Listing",
        },
    ]
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
    if links.get("launchpad"):
        rows.append(
            {
                "project_id": project_id,
                "platform": "Launchpad",
                "value": links["launchpad"],
                "role": "Sale",
            }
        )

    for row in rows:
        try:
            supabase.table("contacts").insert(row).execute()
        except Exception as exc:
            err = str(exc).lower()
            if "duplicate" not in err and "unique" not in err:
                print(f"    [WARN contacts] {row['platform']}: {exc}")


def find_existing_project(
    name: str, chain: str | None, website: str | None
) -> str | None:
    queries = [("name", name)]
    if website:
        queries.append(("website", website))

    for field, value in queries:
        if not value:
            continue
        query = supabase.table("projects").select("id").eq(field, value)
        if field == "name" and chain:
            query = query.eq("chain", chain)
        res = query.limit(1).execute()
        rows = res.data or []
        if rows:
            return rows[0]["id"]
    return None


def parse_upcoming_rows(soup: BeautifulSoup) -> list[dict]:
    rows = []
    for row in soup.select(".Tbl-Row"):
        link = row.select_one(".Cll-Project__link")
        name_node = row.select_one(".Cll-Project__name")
        if not link or not name_node:
            continue

        name = name_node.get_text(" ", strip=True)
        ticker = (
            (row.select_one(".Cll-Project__ticker") or {}).get_text(" ", strip=True)
            if row.select_one(".Cll-Project__ticker")
            else ""
        )
        round_text = (
            (row.select_one(".Tbl-Row__item--round .Cll-Value") or {}).get_text(
                " ", strip=True
            )
            if row.select_one(".Tbl-Row__item--round .Cll-Value")
            else ""
        )
        valuation_text = (
            (row.select_one(".Tbl-Row__item--pre-valuation .Cll-Value") or {}).get_text(
                " ", strip=True
            )
            if row.select_one(".Tbl-Row__item--pre-valuation .Cll-Value")
            else ""
        )
        date_text = (
            (row.select_one(".Tbl-Row__item--date time") or {}).get_text(
                " ", strip=True
            )
            if row.select_one(".Tbl-Row__item--date time")
            else ""
        )
        chain_img = row.select_one(".Tbl-Row__item--ecosystem img")
        chain = normalize_chain(chain_img.get("alt", "") if chain_img else "")
        project_url = urljoin(BASE_URL, link.get("href", ""))

        rows.append(
            {
                "name": name,
                "ticker": ticker,
                "chain": chain,
                "round": round_text,
                "launch_date": parse_launch_date(date_text),
                "launch_date_raw": date_text,
                "valuation": parse_money(valuation_text),
                "project_url": project_url,
            }
        )
    return rows


def save_project(project: dict) -> bool:
    links = extract_detail_links(project["project_url"])
    project_data = {
        "name": project["name"],
        "ticker": project["ticker"],
        "website": links.get("website") or project["project_url"],
        "mcap": project["valuation"],
        "chain": project["chain"],
        "source": "ICO Drops",
        "is_priority": True,
    }
    if PROJECT_OPTIONAL_COLUMNS["is_upcoming"]:
        project_data["is_upcoming"] = True
    if PROJECT_OPTIONAL_COLUMNS["launch_date"]:
        project_data["launch_date"] = project["launch_date"]
    if PROJECT_OPTIONAL_COLUMNS["launchpad"]:
        project_data["launchpad"] = links.get("launchpad")

    existing_id = find_existing_project(
        project["name"], project["chain"], links.get("website")
    )
    try:
        if existing_id:
            supabase.table("projects").update(project_data).eq(
                "id", existing_id
            ).execute()
            project_id = existing_id
        else:
            project_data["status"] = "not_contacted"
            res = supabase.table("projects").insert(project_data).execute()
            project_id = res.data[0]["id"] if res.data else None
        if project_id:
            save_contacts(project_id, project["project_url"], links)
        return True
    except Exception as exc:
        print(f"  [ERROR] {project['name']}: {exc}")
        return False


def run(limit: int = 40):
    print(f"\n{'=' * 60}")
    print(f"  TTM Upcoming Scraper — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}\n")

    soup = fetch_soup(UPCOMING_URL)
    projects = parse_upcoming_rows(soup)[:limit]
    print(f"[INFO] Upcoming projects found: {len(projects)}\n")

    saved = 0
    for project in projects:
        ok = save_project(project)
        if ok:
            saved += 1
            launch_text = project["launch_date_raw"] or "Upcoming"
            chain = project["chain"] or "Unknown"
            print(
                f"  [UPCOMING] {project['name']} ({project['ticker'] or '?'}) | {chain} | {launch_text}"
            )
        time.sleep(1.0)

    print(f"\n{'=' * 60}")
    print(f"  Done! Upcoming projects processed: {saved}")
    print(f"{'=' * 60}\n")
    return saved


if __name__ == "__main__":
    run()
