import os
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client
from dotenv import load_dotenv

import ai_generator
import sender

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Configurable limits via env vars
DAILY_LIMIT = int(os.getenv("OUTREACH_DAILY_LIMIT", "50"))
FOLLOWUP_LIMIT = int(os.getenv("OUTREACH_FOLLOWUP_LIMIT", "30"))
FOLLOWUP_1_DAYS = int(os.getenv("FOLLOWUP_1_DAYS", "4"))
FOLLOWUP_2_DAYS = int(os.getenv("FOLLOWUP_2_DAYS", "10"))

# Warm-up: ramp up sending volume over first 14 days
# Set OUTREACH_START_DATE to the date you first enabled outreach (YYYY-MM-DD)
# During warm-up, daily limit = min(DAILY_LIMIT, 10 + days_since_start * 5)
WARMUP_START = os.getenv("OUTREACH_START_DATE", "")


def get_warmup_limit() -> int:
    """Calculate effective daily limit based on warm-up schedule."""
    if not WARMUP_START:
        return DAILY_LIMIT
    try:
        start = datetime.strptime(WARMUP_START, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        days_active = (datetime.now(timezone.utc) - start).days
        if days_active < 0:
            return 10
        warmup_cap = 10 + (days_active * 5)
        return min(DAILY_LIMIT, warmup_cap)
    except ValueError:
        return DAILY_LIMIT


def has_project_column(column: str) -> bool:
    try:
        supabase.table("projects").select(f"id, {column}").limit(1).execute()
        return True
    except Exception:
        return False


PROJECT_HAS_IS_UPCOMING = has_project_column("is_upcoming")
PROJECT_HAS_LAUNCH_DATE = has_project_column("launch_date")
PROJECT_HAS_LAUNCHPAD = has_project_column("launchpad")


def get_already_emailed() -> set[str]:
    """Get set of email addresses we've already sent Stage 1 to."""
    try:
        res = (
            supabase.table("outreach_logs")
            .select("contacts!inner(value, platform)")
            .eq("stage", "Stage 1 (Cold)")
            .limit(5000)
            .execute()
        )
        emails = set()
        for log in res.data or []:
            contact = log.get("contacts", {})
            if contact.get("platform") == "Email" and contact.get("value"):
                emails.add(contact["value"].lower())
        return emails
    except Exception as e:
        print(f"[WARN] Could not load sent emails for dedup: {e}")
        return set()


def run_outreach_cycle():
    """
    Main function: sends Stage 1 cold emails and follow-ups.
    """
    print("\n" + "=" * 50)
    print("TTM Auto-Pilot: Outreach Cycle Started")
    print("=" * 50)

    effective_limit = get_warmup_limit()
    print(f"Daily limit: {effective_limit} (configured: {DAILY_LIMIT})")
    if WARMUP_START:
        try:
            start = datetime.strptime(WARMUP_START, "%Y-%m-%d")
            days = (datetime.utcnow() - start).days
            print(f"Warm-up day {days} (start: {WARMUP_START})")
        except ValueError:
            pass

    handle_stage_1(effective_limit)
    handle_followups()

    print("\nOutreach Cycle Completed\n")


def handle_stage_1(daily_limit: int):
    print(f"\n--- Processing Stage 1 (Cold) [limit: {daily_limit}] ---")

    try:
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

    already_emailed = get_already_emailed()
    print(f"Dedup: {len(already_emailed)} emails already contacted")

    sent_count = 0
    skipped_dedup = 0
    contacted_domains = set()

    for p in projects:
        if sent_count >= daily_limit:
            print(f"Reached daily limit of {daily_limit} cold emails. Stopping Stage 1.")
            break

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

        # Pick best contact (prefer Founder/BD)
        target_contact = contacts[0]
        for c in contacts:
            if c.get("role") and c["role"] in ["Founder", "BD / Partnerships"]:
                target_contact = c
                break

        email_val = target_contact["value"].lower()

        # Dedup: skip if we've already emailed this address
        if email_val in already_emailed:
            skipped_dedup += 1
            continue

        # Validate email before sending
        if not sender.validate_email(email_val):
            print(f"Skipping {p['name']} - invalid email: {email_val}")
            continue

        # MX validation
        if not sender.check_mx(email_val):
            print(f"Skipping {p['name']} - no MX records for {email_val}")
            continue

        # Domain dedup within this run
        if "@" in email_val:
            domain = email_val.split("@")[1]
            if domain in contacted_domains and domain not in [
                "gmail.com",
                "yahoo.com",
                "outlook.com",
                "hotmail.com",
                "proton.me",
            ]:
                print(f"Skipping {p['name']} - already contacted domain {domain} in this run.")
                continue
            contacted_domains.add(domain)

        print(f"\nTargeting {p['name']} via Email: {target_contact['value']}")

        is_upcoming = bool(p.get("is_upcoming") or p.get("source") == "ICO Drops")

        icebreaker = ai_generator.generate_icebreaker(
            name=p["name"],
            chain=p.get("chain", ""),
            mcap=p.get("mcap", 0),
            contact_name=target_contact.get("contact_name", ""),
            is_upcoming=is_upcoming,
            launchpad=p.get("launchpad", ""),
        )

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
            supabase.table("outreach_logs").insert(
                {
                    "contact_id": target_contact["id"],
                    "stage": "Stage 1 (Cold)",
                    "message_sent": email_content["text"],
                }
            ).execute()

            supabase.table("projects").update({"status": "contacted"}).eq(
                "id", p["id"]
            ).execute()
            print(f"  -> Stage 1 sent to {p['name']}!")
            sent_count += 1
            already_emailed.add(email_val)

    print(f"Stage 1 total sent: {sent_count} (skipped dedup: {skipped_dedup})")


def handle_followups():
    print("\n--- Processing Follow-ups ---")

    try:
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        logs_res = (
            supabase.table("outreach_logs")
            .select(
                "*, contacts!inner(id, project_id, platform, value, contact_name, projects!inner(id, name, ticker, status))"
            )
            .gte("sent_at", thirty_days_ago)
            .order("sent_at", desc=True)
            .limit(2500)
            .execute()
        )

        all_logs = logs_res.data or []
    except Exception as e:
        print(f"[ERROR] Failed to fetch outreach logs: {e}")
        return

    latest_logs_by_project = {}
    for log in all_logs:
        if not log.get("contacts"):
            continue
        pid = log["contacts"]["project_id"]
        project_status = log["contacts"]["projects"]["status"]
        if project_status in ["replied", "no_response"]:
            continue

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

    now = datetime.utcnow().replace(tzinfo=None)
    followup_count = 0

    for pid, log in latest_logs_by_project.items():
        if followup_count >= FOLLOWUP_LIMIT:
            print(f"Reached follow-up limit of {FOLLOWUP_LIMIT}. Stopping.")
            break

        log_time = datetime.fromisoformat(log["sent_at"].replace("Z", "")[:19])
        days_ago = (now - log_time).days

        stage = log["stage"]
        project = log["contacts"]["projects"]
        target_contact = log["contacts"]

        stage_to_send = None
        email_content = None

        if stage == "Stage 1 (Cold)" and days_ago >= FOLLOWUP_1_DAYS:
            stage_to_send = "Follow-up 1"
            email_content = sender.build_followup1_email(
                project["name"],
                project.get("ticker", ""),
                target_contact.get("contact_name", ""),
            )
            new_project_status = "follow_up"
        elif stage == "Follow-up 1" and days_ago >= FOLLOWUP_2_DAYS:
            stage_to_send = "Follow-up 2"
            email_content = sender.build_followup2_email(
                project["name"],
                project.get("ticker", ""),
                target_contact.get("contact_name", ""),
            )
            new_project_status = "no_response"

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
