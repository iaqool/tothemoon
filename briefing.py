"""
TTM Lead Gen — Ежедневный брифинг
Запускай каждое утро: py briefing.py

Показывает:
  - Новые проекты за последние 24 часа
  - Кому нужно написать follow-up (4+ дней без ответа)
  - Общая статистика воронки
"""

import os
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

FOLLOWUP_DAYS = 4
NOW = datetime.now(timezone.utc)

# ── Colors for terminal ──────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
PURPLE = "\033[95m"
RED    = "\033[91m"
GRAY   = "\033[90m"
ORANGE = "\033[33m"

def colored(text, color): return f"{color}{text}{RESET}"
def bold(text): return f"{BOLD}{text}{RESET}"

def fmt_mcap(val):
    if not val or val == 0: return "—"
    if val >= 1e9: return f"${val/1e9:.2f}B"
    if val >= 1e6: return f"${val/1e6:.2f}M"
    if val >= 1e3: return f"${val/1e3:.1f}K"
    return f"${val:,.0f}"

def days_ago(date_str):
    if not date_str: return None
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    return (NOW - dt).days

def print_separator(char="─", width=64):
    print(colored(char * width, GRAY))

def print_header():
    print()
    print_separator("═")
    print(f"  {bold(colored('🚀 TOTHEMOON LEAD GEN', PURPLE))}  {colored('—  Ежедневный брифинг', GRAY)}")
    print(f"  {colored(NOW.strftime('%d %B %Y, %H:%M UTC'), GRAY)}")
    print_separator("═")
    print()

# ── 1. Статистика воронки ────────────────────────────────────────────────────
def print_funnel_stats():
    res = supabase.from_("projects").select("status, is_priority").execute()
    projects = res.data or []

    total      = len(projects)
    priority   = sum(1 for p in projects if p["is_priority"])
    contacted  = sum(1 for p in projects if p["status"] in ("contacted","follow_up","replied"))
    replied    = sum(1 for p in projects if p["status"] == "replied")
    no_resp    = sum(1 for p in projects if p["status"] == "no_response")
    conv       = round(replied / contacted * 100) if contacted > 0 else 0

    print(f"  {bold('📊 СТАТИСТИКА ВОРОНКИ')}")
    print_separator()
    print(f"  {'Всего проектов':<25} {bold(str(total))}")
    print(f"  {'🔥 Приоритетных':<25} {colored(str(priority), PURPLE)}")
    print(f"  {'📤 Написали':<25} {colored(str(contacted), BLUE)}")
    print(f"  {'✅ Ответили':<25} {colored(str(replied), GREEN)}")
    print(f"  {'❌ Нет ответа':<25} {colored(str(no_resp), RED)}")
    print(f"  {'📈 Конверсия':<25} {colored(f'{conv}%', GREEN if conv > 10 else ORANGE)}")
    print()

# ── 2. Новые проекты за 24 часа ─────────────────────────────────────────────
def print_new_projects():
    since = (NOW - timedelta(hours=24)).isoformat()
    res = supabase.from_("projects").select("name, ticker, chain, mcap, is_priority") \
        .gte("created_at", since).order("is_priority", desc=True).execute()
    new_ = res.data or []

    print(f"  {bold('🆕 НОВЫЕ ПРОЕКТЫ (последние 24ч)')}  {colored(f'({len(new_)})', GRAY)}")
    print_separator()

    if not new_:
        print(f"  {colored('Новых проектов нет. Скрапер ещё не запускался?', GRAY)}")
    else:
        for p in new_:
            star  = colored("★", ORANGE) if p["is_priority"] else " "
            name  = bold(p["name"])
            tick  = colored(f"${p['ticker']}", GRAY)
            chain = colored(f"[{p['chain'] or '?'}]", PURPLE if p["is_priority"] else BLUE)
            mcap  = colored(fmt_mcap(p["mcap"]), GREEN)
            print(f"  {star} {name} {tick}  {chain}  {mcap}")
    print()

# ── 3. Follow-up напоминания ─────────────────────────────────────────────────
def print_followups():
    # Статус contacted/follow_up
    res = supabase.from_("projects") \
        .select("id, name, ticker, chain, is_priority") \
        .in_("status", ["contacted", "follow_up"]).execute()
    candidates = res.data or []

    if not candidates:
        print(f"  {bold('⏰ FOLLOW-UP')}")
        print_separator()
        print(f"  {colored('Нет проектов в статусе «Написали» или «Follow-up»', GRAY)}")
        print()
        return

    # Загружаем последние логи аутрича для этих проектов
    project_ids = [p["id"] for p in candidates]
    # Получаем контакты
    cont_res = supabase.from_("contacts").select("id, project_id").in_("project_id", project_ids).execute()
    contacts = cont_res.data or []
    contact_map = {}   # project_id → [contact_ids]
    for c in contacts:
        contact_map.setdefault(c["project_id"], []).append(c["id"])

    all_contact_ids = [c["id"] for c in contacts]
    log_res = (supabase.from_("outreach_logs")
        .select("contact_id, stage, sent_at")
        .in_("contact_id", all_contact_ids)
        .order("sent_at", desc=True)
        .execute()) if all_contact_ids else None

    # Маппинг contact_id → project_id
    cid_to_pid = {c["id"]: c["project_id"] for c in contacts}
    latest_log = {}   # project_id → log
    for log in (log_res.data or []):
        pid = cid_to_pid.get(log["contact_id"])
        if pid and pid not in latest_log:
            latest_log[pid] = log

    # Фильтруем — кому пора писать
    due = []
    for p in candidates:
        log = latest_log.get(p["id"])
        d = days_ago(log["sent_at"]) if log else None
        if d is None or d >= FOLLOWUP_DAYS:
            due.append((p, log, d))

    print(f"  {bold('⏰ FOLLOW-UP СЕГОДНЯ')}  {colored(f'({len(due)} из {len(candidates)})', ORANGE if due else GRAY)}")
    print_separator()

    if not due:
        print(f"  {colored('Все актуальны! Follow-up не нужен 🎉', GREEN)}")
    else:
        for (p, log, d) in sorted(due, key=lambda x: -(x[2] or 999)):
            star  = colored("★", ORANGE) if p["is_priority"] else " "
            name  = bold(p["name"])
            tick  = colored(f"${p['ticker']}", GRAY)
            chain = colored(f"[{p['chain'] or '?'}]", PURPLE if p["is_priority"] else BLUE)
            if d is None:
                age = colored("(никогда не писали?)", RED)
            elif d >= 10:
                age = colored(f"({d} дн. назад — СРОЧНО)", RED)
            elif d >= FOLLOWUP_DAYS:
                age = colored(f"({d} дн. назад)", ORANGE)
            last_stage = colored(f"← {log['stage']}", GRAY) if log else ""
            print(f"  {star} {name} {tick}  {chain}  {age}  {last_stage}")
    print()

# ── 4. Топ приоритетных без контакта ────────────────────────────────────────
def print_untouched_priority():
    res = supabase.from_("projects") \
        .select("name, ticker, chain, mcap") \
        .eq("status", "not_contacted") \
        .eq("is_priority", True) \
        .order("mcap", desc=True) \
        .limit(5) \
        .execute()
    items = res.data or []

    print(f"  {bold('🎯 ТОП ПРИОРИТЕТНЫХ БЕЗ КОНТАКТА')}")
    print_separator()

    if not items:
        print(f"  {colored('Все приоритетные проекты охвачены!', GREEN)}")
    else:
        for i, p in enumerate(items, 1):
            name  = bold(p["name"])
            tick  = colored(f"${p['ticker']}", GRAY)
            chain = colored(f"[{p['chain']}]", PURPLE)
            mcap  = colored(fmt_mcap(p["mcap"]), GREEN)
            print(f"  {colored(str(i)+'.', GRAY)} {name} {tick}  {chain}  {mcap}")
    print()

# ── Main ─────────────────────────────────────────────────────────────────────
def run():
    print_header()
    print_funnel_stats()
    print_new_projects()
    print_followups()
    print_untouched_priority()
    print_separator("═")
    print(f"  {colored('Dashboard:', GRAY)} http://localhost:5173")
    print(f"  {colored('Scraper:  ', GRAY)} py scraper.py")
    print_separator("═")
    print()

if __name__ == "__main__":
    run()
