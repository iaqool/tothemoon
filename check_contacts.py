import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Get all contacts
contacts = (
    supabase.table("contacts").select("id, platform, role", count="exact").execute()
)

print(f"Total contacts: {contacts.count}")

# Count by platform
platforms = {}
roles = {}

for c in contacts.data:
    platform = c["platform"]
    role = c.get("role", "Unknown")
    platforms[platform] = platforms.get(platform, 0) + 1
    roles[role] = roles.get(role, 0) + 1

print("\nBy Platform:")
for k, v in sorted(platforms.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v}")

print("\nBy Role:")
for k, v in sorted(roles.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v}")

# Get projects with contacts
projects_with_contacts = (
    supabase.table("projects").select("id", count="exact").execute()
)
print(f"\nTotal projects: {projects_with_contacts.count}")
