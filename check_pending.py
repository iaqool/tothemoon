import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

res = supabase.table("projects").select("id, name, status").eq("status", "not_contacted").execute()
print(f"Total not_contacted projects: {len(res.data)}")

contacts = supabase.table("contacts").select("*").in_("platform", ["Email"]).execute()
print(f"Total email contacts: {len(contacts.data)}")
