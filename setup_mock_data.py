import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

projects = supabase.table("projects").select("id, name").eq("status", "not_contacted").order("mcap", desc=True).limit(3).execute()

for p in projects.data:
    print(f"Adding mock email to {p['name']}")
    supabase.table("contacts").insert({
        "project_id": p["id"],
        "platform": "Email",
        "value": f"founder@{p['name'].replace(' ', '').lower()}.com",
        "role": "Founder",
        "contact_name": "Johnny"
    }).execute()
