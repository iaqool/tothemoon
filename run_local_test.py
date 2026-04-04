import os
import sys
from datetime import datetime
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

# Убираем Resend ключ для MOCK режима
os.environ["RESEND_API_KEY"] = ""

supabase = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
replied_before = supabase.table('projects').select('id', count='exact').eq('status', 'replied').execute().count or 0
start_time = datetime.utcnow().isoformat() + "+00:00"

print("--- RUNNING OUTREACH IN MOCK MODE ---")
import auto_outreach
auto_outreach.run_outreach_cycle()

print("\n--- GENERATING OUTREACH SUMMARY ---")
replied_after = supabase.table('projects').select('id', count='exact').eq('status', 'replied').execute().count or 0
replied_delta = replied_after - replied_before

res = (
    supabase.table('outreach_logs')
    .select('id, stage, contacts!inner(project_id, value, projects!inner(name, chain, mcap, is_upcoming))')
    .gte('sent_at', start_time)
    .execute()
)
logs = res.data or []

stage1_count = 0
followup1_count = 0
followup2_count = 0
whales_count = 0
solana_count = 0
ton_count = 0
base_count = 0
upcoming_count = 0

all_contacted_projects = []

for log in logs:
    stage = log.get('stage', '')
    if stage == 'Stage 1 (Cold)': stage1_count += 1
    elif stage == 'Follow-up 1': followup1_count += 1
    elif stage == 'Follow-up 2': followup2_count += 1
    
    contact = log.get('contacts', {})
    project = contact.get('projects', {})
    chain = project.get('chain', '')
    mcap = float(project.get('mcap') or 0)
    is_upcoming = project.get('is_upcoming') is True
    
    if stage == 'Stage 1 (Cold)':
        all_contacted_projects.append({'name': project.get('name'), 'mcap': mcap, 'chain': chain})
        if mcap > 1000000: whales_count += 1
        if chain == 'Solana': solana_count += 1
        if chain == 'TON': ton_count += 1
        if chain == 'Base': base_count += 1
        if is_upcoming: upcoming_count += 1

all_contacted_projects.sort(key=lambda x: x['mcap'], reverse=True)
top_opps = all_contacted_projects[:3]

print("\n## 🚀 TTM Pipeline 3.0: Outreach Report\n")
print("### 📊 Overview")
print(f"- 📨 **Stage 1 Sent:** {stage1_count}")
print(f"- ⏳ **Follow-ups Sent:** {followup1_count + followup2_count}")
print(f"- 🤝 **Net New Replies:** {replied_delta}\n")

print("### 🎯 Ecosystem Split (Stage 1)")
print(f"- **Solana:** {solana_count}")
print(f"- **TON:** {ton_count}")
print(f"- **Base:** {base_count}")
print(f"- **Other:** {stage1_count - solana_count - ton_count - base_count}\n")

print("### 🐋 Lead Quality")
print(f"- **Whales Contacted (MCap > $1M):** {whales_count}")
print(f"- **Pre-launch Leads (Upcoming):** {upcoming_count}\n")

if top_opps:
    print("### 🌟 Top Opportunities")
    for idx, op in enumerate(top_opps, 1):
        print(f"{idx}. **{op['name']}** ({op['chain']}) — MCap: ${op['mcap']:,.0f}")
else:
    print("### 🌟 Top Opportunities\n- No new projects contacted today.\n")
