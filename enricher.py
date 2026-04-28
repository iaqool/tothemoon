"""
TTM Lead Gen — Contact Enricher
================================
Ищет конкретных людей (BD, Founder, Partnerships) для каждого проекта:
  1. Поиск X (Twitter) профилей через Serper.dev
  2. Опциональный LinkedIn для уточнения имени/должности
  3. Парсинг сайта проекта (Footer, About, GitBook) на предмет bd@/partnerships@ email
  4. Сохранение всех найденных контактов в таблицу contacts с полем role

Запуск: py enricher.py
  Или через pipeline.py (автоматически)
"""

import os
import re
import sys
import time
import json
import socket
import ipaddress
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── Supabase ─────────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Serper.dev Search API ─────────────────────────────────────────────────────
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
SERPER_URL = "https://google.serper.dev/search"

# ── Конфигурация ──────────────────────────────────────────────────────────────
TARGET_ROLES = [
    "founder",
    "co-founder",
    "bd",
    "business development",
    "partnerships",
    "growth",
    "listing",
]
PRIORITY_ROLES = {"founder", "co-founder", "bd", "business development", "partnerships"}
PERSONAL_ROLES = {
    "Founder",
    "BD / Partnerships",
    "Listing Manager",
    "Growth / Marketing",
}
PLATFORM_PRIORITY = {"Email": 0, "LinkedIn": 1, "X / Twitter": 2, "Telegram": 3}
EMAIL_LOCAL_HINTS = (
    "bd",
    "bizdev",
    "business",
    "partner",
    "partnership",
    "listing",
    "growth",
    "marketing",
    "hello",
    "contact",
    "info",
)
EMAIL_CONTEXT_HINTS = (
    "partnership",
    "partner",
    "listing",
    "market making",
    "liquidity",
    "business development",
    "bd",
    "marketing",
    "media kit",
    "press",
    "contact us",
)

BD_EMAIL_REGEX = re.compile(
    r"(bd|partnerships?|listing|growth)[\w.+-]*@[\w.-]+\.\w+", re.IGNORECASE
)
GENERIC_EMAIL_REGEX = re.compile(
    r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE
)
X_HANDLE_REGEX = re.compile(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]{1,50})(?:[/?]|$)")
TG_HANDLE_REGEX = re.compile(r"(?:t\.me|telegram\.me)/([A-Za-z0-9_]{3,50})(?:[/?]|$)")
ROLE_DETECT_REGEX = re.compile(r"\b(" + "|".join(TARGET_ROLES) + r")\b", re.IGNORECASE)
NAME_CLEAN_REGEX = re.compile(r"[^a-zA-Z\u00C0-\u024F\s'-]")
DOC_LINK_HINTS = (
    "docs",
    "doc",
    "gitbook",
    "litepaper",
    "whitepaper",
    "media",
    "press",
    "kit",
    "brand",
    "partner",
    "contact",
    "team",
    "about",
)


# ─── SSRF Protection ──────────────────────────────────────────────────────────
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def is_safe_url(url: str) -> bool:
    """Validate URL is safe to fetch (not internal/private)."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        # Block cloud metadata endpoints
        if hostname in ("metadata.google.internal", "metadata"):
            return False
        addrs = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in addrs:
            ip = ipaddress.ip_address(sockaddr[0])
            for network in _BLOCKED_NETWORKS:
                if ip in network:
                    return False
        return True
    except Exception:
        return False


# ─── Search Engine Helper ─────────────────────────────────────────────────────
def serper_search(query: str, num: int = 5) -> list[dict]:
    """Запрос к Serper.dev Google Search API."""
    if not SERPER_API_KEY:
        print("  [WARN] SERPER_API_KEY не задан — пропускаем поиск.")
        return []
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    payload = {"q": query, "num": num, "gl": "us", "hl": "en"}
    try:
        r = requests.post(SERPER_URL, headers=headers, json=payload, timeout=15)
        r.raise_for_status()
        return r.json().get("organic", [])
    except Exception as e:
        print(f"  [ERR Serper] {e}")
        return []


def extract_x_handles(results: list[dict]) -> list[dict]:
    """Ищем X-хендлы в заголовках, ссылках и сниппетах поисковой выдачи."""
    found = []
    seen = set()
    for r in results:
        link = r.get("link", "")
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        full_text = f"{link} {title} {snippet}"

        # Прямой матч ссылки x.com/handle или twitter.com/handle
        for m in X_HANDLE_REGEX.finditer(full_text):
            handle = m.group(1).lower()
            if handle in {
                "home",
                "search",
                "intent",
                "i",
                "hashtag",
                "share",
                "notifications",
            }:
                continue
            if handle in seen:
                continue
            seen.add(handle)

            # Определяем роль из контекста
            role = detect_role(f"{title} {snippet}")
            name = extract_name_from_snippet(snippet)

            found.append(
                {
                    "handle": f"https://x.com/{m.group(1)}",
                    "platform": "X / Twitter",
                    "role": role,
                    "name": name,
                }
            )
    return found


def extract_telegram_handles(results: list[dict]) -> list[dict]:
    """Ищем Telegram-хендлы."""
    found = []
    seen = set()
    for r in results:
        full_text = f"{r.get('link', '')} {r.get('title', '')} {r.get('snippet', '')}"
        for m in TG_HANDLE_REGEX.finditer(full_text):
            handle = m.group(1).lower()
            if handle in seen:
                continue
            seen.add(handle)
            role = detect_role(f"{r.get('title', '')} {r.get('snippet', '')}")
            name = extract_name_from_snippet(r.get("snippet", ""))
            found.append(
                {
                    "handle": f"https://t.me/{m.group(1)}",
                    "platform": "Telegram",
                    "role": role,
                    "name": name,
                }
            )
    return found


def detect_role(text: str) -> str:
    """Определяем роль человека из текста сниппета."""
    lower = text.lower()
    if re.search(r"\bfounder\b|\bco-founder\b|\bceo\b", lower):
        return "Founder"
    if re.search(r"\bpartnership|\bbd\b|\bbusiness development\b", lower):
        return "BD / Partnerships"
    if re.search(r"\blisting\b|\bexchange\b", lower):
        return "Listing Manager"
    if re.search(r"\bgrowth\b|\bcmo\b|\bmarketing\b", lower):
        return "Growth / Marketing"
    return "Team Member"


def extract_name_from_snippet(snippet: str) -> str:
    """Эвристика: первые 1-2 слова с заглавной буквой до слов-роли."""
    m = re.match(r"^([A-Z][a-z]+ (?:[A-Z][a-z]+)?) [|\-–—]", snippet)
    if m:
        name = NAME_CLEAN_REGEX.sub("", m.group(1)).strip()
        return name if len(name) < 40 else ""
    return ""


# ─── Website BD Email Parser ──────────────────────────────────────────────────
def get_project_website(project: dict) -> str:
    """Берем реальный website из contacts, если в project лежит CoinGecko URL."""
    website = (project.get("website") or "").strip()
    if website and "coingecko.com" not in website:
        return website

    try:
        res = (
            supabase.table("contacts")
            .select("value")
            .eq("project_id", project["id"])
            .eq("platform", "Website")
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0]["value"] if rows else website
    except Exception:
        return website


def fetch_page(url: str, headers: dict) -> tuple[str, BeautifulSoup | None]:
    if not is_safe_url(url):
        return "", None
    try:
        r = requests.get(url, headers=headers, timeout=8, allow_redirects=False)
        if r.status_code != 200 or "text/html" not in r.headers.get("Content-Type", ""):
            return "", None
        return r.text, BeautifulSoup(r.text, "html.parser")
    except Exception:
        return "", None


def discover_related_pages(website_url: str, headers: dict) -> list[str]:
    """Ищем docs/gitbook/media-kit/partners страницы с homepage и стандартных путей."""
    if not website_url:
        return []

    parsed = urlparse(website_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    candidates = [website_url]
    for path in [
        "/about",
        "/team",
        "/contact",
        "/docs",
        "/documentation",
        "/partners",
        "/partnerships",
        "/media-kit",
        "/press",
        "/brand",
    ]:
        candidates.append(f"{base}{path}")

    html, soup = fetch_page(website_url, headers)
    if soup:
        for a in soup.select("a[href]"):
            href = (a.get("href") or "").strip()
            text = " ".join(
                filter(None, [href.lower(), a.get_text(" ", strip=True).lower()])
            )
            if not href or href.startswith("#"):
                continue
            if any(hint in text for hint in DOC_LINK_HINTS):
                candidates.append(urljoin(website_url, href))

    seen = set()
    deduped = []
    for url in candidates:
        clean = url.split("#", 1)[0]
        if clean not in seen:
            seen.add(clean)
            deduped.append(clean)
    return deduped[:12]


def classify_email_role(email: str, page_text: str) -> str | None:
    local = email.split("@", 1)[0].lower()
    context = page_text.lower()

    if any(
        hint in local for hint in ("bd", "bizdev", "business", "partner", "partnership")
    ):
        return "BD / Partnerships"
    if any(hint in local for hint in ("listing", "exchange")):
        return "Listing Manager"
    if any(hint in local for hint in ("growth", "marketing")):
        return "Growth / Marketing"
    if any(hint in local for hint in ("hello", "contact", "info")):
        if any(hint in context for hint in EMAIL_CONTEXT_HINTS):
            return "BD / Partnerships"
    return None


def extract_relevant_emails(page_text: str) -> list[dict]:
    candidates = []
    seen = set()
    for match in GENERIC_EMAIL_REGEX.finditer(page_text):
        email = match.group(0).strip().lower().rstrip(".,:;)]}\"'")
        if email in seen:
            continue
        if any(part in email for part in ("noreply@", "no-reply@", "donotreply@")):
            continue

        role = classify_email_role(email, page_text)
        if not role:
            continue

        seen.add(email)
        candidates.append(
            {
                "handle": email,
                "platform": "Email",
                "role": role,
                "name": "",
            }
        )
    return candidates


def find_bd_email_on_site(website_url: str) -> list[dict]:
    """
    Пробуем найти bd@/partnerships@ прямо на сайте проекта.
    Проверяем homepage, docs/gitbook, media-kit, partners, about/team/contact.
    """
    if not website_url:
        return []
    results = []

    headers = {"User-Agent": "Mozilla/5.0 (compatible; TTMLeadBot/1.0)"}
    for url in discover_related_pages(website_url, headers):
        html, soup = fetch_page(url, headers)
        if not html:
            continue

        results.extend(extract_relevant_emails(html))

        if soup:
            for a in soup.select("a[href^='mailto:']"):
                href = a.get("href", "")
                email = href.replace("mailto:", "").split("?", 1)[0].strip().lower()
                role = classify_email_role(email, soup.get_text(" ", strip=True))
                if role:
                    results.append(
                        {
                            "handle": email,
                            "platform": "Email",
                            "role": role,
                            "name": "",
                        }
                    )

        if results:
            break

    # Дедупликация
    seen = set()
    deduped = []
    for r in results:
        if r["handle"] not in seen:
            seen.add(r["handle"])
            deduped.append(r)
    return deduped


# ─── Save to Supabase ─────────────────────────────────────────────────────────
def save_individual_contacts(project_id: str, candidates: list[dict]):
    """Сохраняем каждый найденный контакт как отдельную строку в contacts."""
    if not candidates:
        return 0

    # Подготовка всех строк для batch insert
    rows = [
        {
            "project_id": project_id,
            "platform": c["platform"],
            "value": c["handle"],
            "role": c.get("role", "Team Member"),
            "contact_name": c.get("name") or None,
        }
        for c in candidates
    ]

    # Попытка batch insert
    try:
        result = supabase.table("contacts").insert(rows).execute()
        return len(result.data)
    except Exception as e:
        err = str(e).lower()
        # Если batch insert упал из-за дубликатов, делаем поштучную вставку
        if "duplicate" in err or "unique" in err:
            saved = 0
            for row in rows:
                try:
                    supabase.table("contacts").insert(row).execute()
                    saved += 1
                except Exception as e2:
                    err2 = str(e2).lower()
                    if "duplicate" not in err2 and "unique" not in err2:
                        print(f"    [WARN save] {row['platform']} {row['value']}: {e2}")
            return saved
        else:
            print(f"    [ERROR batch insert] {e}")
            return 0


def has_personal_contact(contact_rows: list[dict]) -> bool:
    return any((row.get("role") or "") in PERSONAL_ROLES for row in contact_rows)


def has_email_contact(contact_rows: list[dict]) -> bool:
    return any(row.get("platform") == "Email" for row in contact_rows)


def get_queue_reason(contact_rows: list[dict], project: dict, email_only: bool) -> str:
    no_email = not has_email_contact(contact_rows)
    no_personal = not has_personal_contact(contact_rows)
    mcap = float(project.get("mcap") or 0)

    if email_only and no_email and mcap > 1_000_000:
        return "High MCap - No Email"
    if email_only and no_email:
        return "Email Hunt"
    if no_email and no_personal and mcap > 1_000_000:
        return "High MCap - No Email / No Decision Maker"
    if no_email and no_personal:
        return "No Email / No Decision Maker"
    if no_personal:
        return "No Decision Maker"
    return "Already Enriched"


# ─── Core Enrichment for a Single Project ────────────────────────────────────
def enrich_project(project: dict, email_only: bool = False) -> int:
    """Возвращает количество новых контактов, добавленных в базу."""
    pid = project["id"]
    name = project["name"]
    ticker = project.get("ticker", "")
    site = get_project_website(project)

    print(f"\n  🔍 {name} ({ticker})")

    all_candidates: list[dict] = []

    if not email_only:
        # 1. X / Twitter — персональные профили
        q_x = f'"{name}" (founder OR BD OR partnerships OR listing) site:x.com'
        results_x = serper_search(q_x, num=6)
        x_handles = extract_x_handles(results_x)
        all_candidates.extend(x_handles)
        time.sleep(0.8)

        # 2. Широкий поиск упоминаний с BD/Telegram
        q_tg = f'"{name}" (BD OR "business development" OR partnerships OR listing) telegram'
        results_tg = serper_search(q_tg, num=5)
        tg_handles = extract_telegram_handles(results_tg)
        all_candidates.extend(tg_handles)
        time.sleep(0.8)

        # 3. LinkedIn profil (уточнение имени — не скрэйпим, ищем в Google index)
        q_li = f'"{name}" (founder OR "head of BD" OR "partnerships manager") site:linkedin.com'
        results_li = serper_search(q_li, num=4)
        # LinkedIn страницы не скрейпим — берём имя из сниппетов
        for r in results_li:
            link = r.get("link", "")
            if "linkedin.com/in/" not in link:
                continue
            name_part = extract_name_from_snippet(r.get("snippet", ""))
            role_part = detect_role(f"{r.get('title', '')} {r.get('snippet', '')}")
            if name_part:
                all_candidates.append(
                    {
                        "handle": link,
                        "platform": "LinkedIn",
                        "role": role_part,
                        "name": name_part,
                    }
                )
        time.sleep(0.8)

    # 4. Email на сайте
    if site and "coingecko.com" not in site:
        emails = find_bd_email_on_site(site)
        all_candidates.extend(emails)

    if not all_candidates:
        print(f"    → Контактов не найдено")
        return 0

    # Приоритизируем: Founder/BD первыми
    def priority_score(c):
        role = c.get("role", "").lower()
        platform_score = PLATFORM_PRIORITY.get(c.get("platform"), 9)
        for p in PRIORITY_ROLES:
            if p in role:
                return (0, platform_score)
        return (1, platform_score)

    all_candidates.sort(key=priority_score)

    saved = save_individual_contacts(pid, all_candidates)
    roles_summary = ", ".join({c.get("role", "?") for c in all_candidates})
    print(
        f"    → Найдено: {len(all_candidates)} контактов ({roles_summary}), сохранено: {saved}"
    )
    return saved


# ─── Main ─────────────────────────────────────────────────────────────────────
def run(
    project_ids: list[str] | None = None, limit: int = 50, email_only: bool = False
):
    """
    Запускает обогащение контактов.
    project_ids: список конкретных ID, иначе берём проекты без индивидуальных контактов.
    limit: максимум проектов за один запуск.
    """
    from datetime import datetime

    print(f"\n{'=' * 60}")
    print(f"  TTM Enricher — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}")

    if project_ids:
        res = supabase.table("projects").select("*").in_("id", project_ids).execute()
        projects = res.data or []
    else:
        # Умная очередь:
        # 1) email_only: только проекты без Email, сначала >$1M
        # 2) обычный режим: сначала проекты >$1M без Email
        # 3) затем проекты без Email и без персонального контакта
        # 4) затем проекты без персонального контакта
        sample_size = max(limit * 5, 100)
        res = (
            supabase.table("projects")
            .select("*")
            .order("is_priority", desc=True)
            .order("mcap", desc=True)
            .limit(sample_size)
            .execute()
        )
        projects = res.data or []

        project_ids_batch = [p["id"] for p in projects]
        contacts_res = (
            (
                supabase.table("contacts")
                .select("project_id, platform, role")
                .in_("project_id", project_ids_batch)
                .execute()
            )
            if project_ids_batch
            else None
        )

        contacts_by_project = {}
        for row in contacts_res.data or []:
            contacts_by_project.setdefault(row["project_id"], []).append(row)

        def queue_score(project: dict):
            project_contacts = contacts_by_project.get(project["id"], [])
            no_email = not has_email_contact(project_contacts)
            no_personal = not has_personal_contact(project_contacts)
            mcap = float(project.get("mcap") or 0)

            if email_only:
                if not no_email:
                    bucket = 9
                elif mcap > 1_000_000:
                    bucket = 0
                else:
                    bucket = 1
            elif mcap > 1_000_000 and no_email:
                bucket = 0
            elif no_email and no_personal:
                bucket = 1
            elif no_personal:
                bucket = 2
            else:
                bucket = 3

            return (bucket, 0 if project.get("is_priority") else 1, -mcap)

        queued = []
        for project in sorted(projects, key=queue_score):
            project_contacts = contacts_by_project.get(project["id"], [])
            if has_personal_contact(project_contacts) and not email_only:
                continue
            if email_only and has_email_contact(project_contacts):
                continue

            project["queue_reason"] = get_queue_reason(
                project_contacts, project, email_only
            )
            queued.append(project)
            if len(queued) >= limit:
                break

        projects = queued
    print(f"[INFO] Проектов для обогащения: {len(projects)}\n")

    total_new = 0
    for p in projects:
        if p.get("queue_reason"):
            print(f"[QUEUE] {p['name']} -> {p['queue_reason']}")
        new = enrich_project(p, email_only=email_only)
        total_new += new
        time.sleep(1.5)  # вежливо относимся к rate-limit

    print(f"\n{'=' * 60}")
    print(f"  Готово! Новых контактов добавлено: {total_new}")
    print(f"{'=' * 60}\n")

    return total_new


if __name__ == "__main__":
    run()
