import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

print("=== RECENT OUTREACH LOGS ===")
logs = supabase.table("outreach_logs").select("*").order("sent_at", desc=True).limit(5).execute()
for row in logs.data:
    print(row)

print("\n=== RECENTLY CONTACTED PROJECTS ===")
projs = supabase.table("projects").select("id, name, status").in_("status", ["contacted", "follow_up", "no_response"]).execute()
for row in projs.data:
    print(row)
