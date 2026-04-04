import os
from datetime import datetime, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv

import ai_generator
import sender

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def has_project_column(column: str) -> bool:
    try:
        supabase.table("projects").select(f"id, {column}").limit(1).execute()
        return True
    except Exception:
        return False


PROJECT_HAS_IS_UPCOMING = has_project_column("is_upcoming")
PROJECT_HAS_LAUNCH_DATE = has_project_column("launch_date")
PROJECT_HAS_LAUNCHPAD = has_project_column("launchpad")


def run_outreach_cycle():
    """
    Основная функция: проверяет проекты и отправляет первую рассылку или follow-ups.
    """
    print("\n" + "=" * 50)
    print("🚀 TTM Auto-Pilot: Outreach Cycle Started")
    print("=" * 50)

    handle_stage_1()
    handle_followups()

    print("\n✅ Outreach Cycle Completed\n")


def handle_stage_1():
    print("\n--- Processing Stage 1 (Cold) ---")
    # Ищем проекты со статусом not_contacted
    try:
        # 1. Приоритетная очередь
        project_fields = ["id", "name", "ticker", "chain", "mcap", "source"]
        if PROJECT_HAS_IS_UPCOMING:
            project_fields.append("is_upcoming")
        if PROJECT_HAS_LAUNCH_DATE:
            project_fields.append("launch_date")
        if PROJECT_HAS_LAUNCHPAD:
            project_fields.append("launchpad")

        res = (
            supabase.table("projects")
            .select(", ".join(project_fields))
            .eq("status", "not_contacted")
            .order("is_priority", desc=True)
            .order("mcap", desc=True)
            .execute()
        )
        projects = res.data or []
    except Exception as e:
        print(f"[ERROR] Failed to fetch projects: {e}")
        return

    if not projects:
        print("No new projects for Stage 1.")
        return

    # дневной или run-лимит
    DAILY_LIMIT = 3
    sent_count = 0
    contacted_domains = set()  # для дедупликации доменов

    for p in projects:
        if sent_count >= DAILY_LIMIT:
            print(
                f"Reached daily limit of {DAILY_LIMIT} cold emails. Stopping Stage 1."
            )
            break

        # Ищем Email контакты для проекта
        try:
            c_res = (
                supabase.table("contacts")
                .select("*")
                .eq("project_id", p["id"])
                .eq("platform", "Email")
                .execute()
            )
            contacts = c_res.data or []
        except Exception as e:
            print(f"[ERROR] Failed to fetch contacts for {p['name']}: {e}")
            continue

        if not contacts:
            continue

        # Выбираем лучший контакт
        target_contact = contacts[0]
        for c in contacts:
            if c.get("role") and c["role"] in ["Founder", "BD / Partnerships"]:
                target_contact = c
                break

        # Проверка домена для предотвращения отправки разным токенам одной команды
        email_val = target_contact["value"].lower()
        if "@" in email_val:
            domain = email_val.split("@")[1]
            if domain in contacted_domains and domain not in [
                "gmail.com",
                "yahoo.com",
                "outlook.com",
                "hotmail.com",
                "proton.me",
            ]:
                print(
                    f"Skipping {p['name']} - already contacted domain {domain} in this run."
                )
                continue
            contacted_domains.add(domain)

        print(f"\nTargeting {p['name']} via Email: {target_contact['value']}")

        is_upcoming = bool(p.get("is_upcoming") or p.get("source") == "ICO Drops")

        # 1. AI Personalization
        icebreaker = ai_generator.generate_icebreaker(
            name=p["name"],
            chain=p.get("chain", ""),
            mcap=p.get("mcap", 0),
            contact_name=target_contact.get("contact_name", ""),
            is_upcoming=is_upcoming,
            launchpad=p.get("launchpad", ""),
        )

        # 2. Build template & Send
        if is_upcoming:
            email_content = sender.build_stage1_upcoming_email(
                icebreaker, p["name"], p.get("ticker", ""), p.get("launchpad", "")
            )
        else:
            email_content = sender.build_stage1_email(
                icebreaker, p["name"], p.get("ticker", "")
            )
        send_res = sender.send_email(
            target_contact["value"],
            email_content["subject"],
            email_content["text"],
            email_content["html"],
        )

        if send_res:
            # 3. Log an entry
            supabase.table("outreach_logs").insert(
                {
                    "contact_id": target_contact["id"],
                    "stage": "Stage 1 (Cold)",
                    "message_sent": email_content["text"],
                }
            ).execute()

            # 4. Update status
            supabase.table("projects").update({"status": "contacted"}).eq(
                "id", p["id"]
            ).execute()
            print(f"  -> Stage 1 sent to {p['name']}!")
            sent_count += 1

    print(f"Stage 1 total sent: {sent_count}")


def handle_followups():
    print("\n--- Processing Follow-ups ---")

    # Чтобы найти проекты для Follow-up, нам нужны контакты, по которым мы уже отправляли письма
    # Более надежный путь: найти последние outreach_logs
    try:
        # Для простоты: берем последние логи (сортировка по sent_at)
        logs_res = (
            supabase.table("outreach_logs")
            .select(
                "*, contacts!inner(project_id, platform, value, contact_name, projects!inner(id, name, ticker, status))"
            )
            .execute()
        )

        all_logs = logs_res.data or []
    except Exception as e:
        print(f"[ERROR] Failed to fetch outreach logs: {e}")
        return

    # Группируем последний лог для каждого проекта (используя contacts.project_id)
    latest_logs_by_project = {}
    for log in all_logs:
        if not log.get("contacts"):
            continue
        pid = log["contacts"]["project_id"]
        # Если проект уже ответил или мы больше не отправляем - пропускаем
        project_status = log["contacts"]["projects"]["status"]
        if project_status in ["replied", "no_response"]:
            continue

        # Проверяем только Email контакты (мы автоматизируем только почту сейчас)
        if log["contacts"]["platform"] != "Email":
            continue

        log_time = datetime.fromisoformat(log["sent_at"].replace("Z", "+00:00"))
        if pid not in latest_logs_by_project:
            latest_logs_by_project[pid] = log
        else:
            existing_time = datetime.fromisoformat(
                latest_logs_by_project[pid]["sent_at"].replace("Z", "+00:00")
            )
            if log_time > existing_time:
                latest_logs_by_project[pid] = log

    now = datetime.utcnow().replace(tzinfo=None)  # условно UTC-naive для сравнения
    followup_count = 0

    for pid, log in latest_logs_by_project.items():
        # Сравниваем даты. Supabase использует UTC
        # Так как datetime.fromisoformat оставляет tzinfo (если оно там было, например +00:00)
        # Приведем к naive для простоты сравнения
        log_time = datetime.fromisoformat(log["sent_at"].replace("Z", "")[:19])
        days_ago = (now - log_time).days

        stage = log["stage"]
        project = log["contacts"]["projects"]
        target_contact = log["contacts"]

        stage_to_send = None
        email_content = None

        if stage == "Stage 1 (Cold)" and days_ago >= 4:
            stage_to_send = "Follow-up 1"
            email_content = sender.build_followup1_email(
                project["name"],
                project.get("ticker", ""),
                target_contact.get("contact_name", ""),
            )
            new_project_status = "follow_up"
        elif stage == "Follow-up 1" and days_ago >= 10:
            stage_to_send = "Follow-up 2"
            email_content = sender.build_followup2_email(
                project["name"],
                project.get("ticker", ""),
                target_contact.get("contact_name", ""),
            )
            new_project_status = "no_response"  # После Follow-up 2 закрываем воронку

        if stage_to_send and email_content:
            print(f"Targeting {project['name']} for {stage_to_send}")
            send_res = sender.send_email(
                target_contact["value"],
                email_content["subject"],
                email_content["text"],
                email_content["html"],
            )
            if send_res:
                supabase.table("outreach_logs").insert(
                    {
                        "contact_id": target_contact["id"],
                        "stage": stage_to_send,
                        "message_sent": email_content["text"],
                    }
                ).execute()

                supabase.table("projects").update({"status": new_project_status}).eq(
                    "id", project["id"]
                ).execute()
                print(f"  -> {stage_to_send} sent to {project['name']}!")
                followup_count += 1

    print(f"Follow-ups total sent: {followup_count}")


if __name__ == "__main__":
    run_outreach_cycle()
