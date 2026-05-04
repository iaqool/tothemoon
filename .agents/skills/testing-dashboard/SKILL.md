# Testing: Tothemoon Dashboard

## Overview
Tothemoon is a crypto BD automation tool with a Vercel-hosted React dashboard. Testing involves verifying UI rendering, tab navigation, data loading from Supabase, and filter functionality.

## Production URL
- **Dashboard:** https://tothemoon-rust.vercel.app/
- **Vercel project:** `tothemoon` (auto-deploys from `main` branch)
- **Preview deploys:** Available on PR branches via Vercel

## Dashboard Structure
- **Header:** Logo + page tabs ("Leads", "📡 TG Signals") + KPI stats bar
- **Leads page (default):** KPI cards, Outreach Feed, filter tabs, project table with contacts
- **TG Signals page:** Signal cards with AI classification, type/channel filters, "Add to Leads" button

## Key Test Scenarios

### 1. Tab Navigation
- Click between "Leads" and "📡 TG Signals" tabs
- Verify active tab has purple background (`var(--accent-purple)`)
- Verify content switches without full page reload
- Verify returning to Leads shows project data

### 2. Leads Page
- KPI cards should show non-zero Total Projects and With Contacts
- Outreach Feed shows recent send events (if any outreach has been done)
- Filter tabs: All Leads, Hot Upcoming, Priority, Medium, Others, Follow-up
- Clicking a filter should change the project count shown
- Project table: name, ticker, network badge, MCap, contacts (emoji links), status dropdown
- Quick filters: Priority, Whales $1M+, Needs Attention, Has Contacts, Has Email

### 3. TG Signals Page
- **Without data (parser not configured):** Shows empty state with 📡 icon, "Нет сигналов", and setup instructions mentioning `TG_CHANNELS` and `TG Signal Parser`
- **With data:** Signal cards grouped by type (TGE/Listing, Activity, Long-term), relevance scores, channel badges, "В лиды" button

## Data Dependencies
- **Leads data** comes from `projects` + `contacts` tables in Supabase (populated by GitHub Actions scraper every 6 hours)
- **TG Signals data** comes from `tg_signals` table (populated by TG parser workflow — requires Telegram credentials)
- **Outreach Feed** comes from `outreach_logs` table (populated by auto_outreach.py)

## Known Gotchas
- TG Signals page might show empty state if the `tg_signals` table doesn't exist yet in Supabase (user needs to run the schema SQL)
- The dashboard has no authentication — anyone with the URL can view data
- Vercel preview deploys use the same Supabase instance as production (env vars are shared)
- The `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` are baked into the frontend build
- If Supabase returns errors, the dashboard silently shows empty states (check browser console for errors)
- Filter buttons work client-side — if data isn't loading, filters won't change anything

## Testing Without Data
When the TG parser hasn't been set up:
- You CAN test: tab navigation, empty state rendering, Leads page functionality, filters
- You CANNOT test: signal cards, type/channel filters, "Add to Leads" flow, relevance scores
- Do NOT try to insert test data without Supabase credentials

## Browser Console Checks
Always check the browser console (`computer` tool with `action=console`) for:
- Supabase connection errors
- JavaScript runtime errors
- Failed network requests

## Devin Secrets Needed
None required for read-only UI testing. The dashboard uses public Supabase anon key embedded in the build.

For full integration testing (inserting test signals), you would need:
- `SUPABASE_URL` — Supabase project URL
- `SUPABASE_SERVICE_KEY` — Service role key for direct DB writes
