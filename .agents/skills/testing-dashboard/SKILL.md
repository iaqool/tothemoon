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
  - Signal cards include clickable contact links: 🌐 Сайт, 𝕏 Twitter, ✈️ Telegram (styled with `.signal-link-web`, `.signal-link-twitter`, `.signal-link-tg`)

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
- **With data:** Signal cards grouped by type (TGE/Listing, Activity, Long-term), relevance scores, channel badges, "В лиды" button, and contact link buttons

### 4. CSS Class Verification
When new CSS classes are added (e.g., for contact links), verify they are deployed by running this in browser console:
```javascript
const sheets = [...document.styleSheets];
const cssClasses = ['signal-links', 'signal-link', 'signal-link-web', 'signal-link-twitter', 'signal-link-tg'];
const results = {};
for (const cls of cssClasses) {
  let found = false;
  for (const sheet of sheets) {
    try {
      const rules = [...sheet.cssRules];
      for (const rule of rules) {
        if (rule.selectorText && rule.selectorText.includes('.' + cls)) {
          found = true;
          break;
        }
      }
    } catch(e) {}
    if (found) break;
  }
  results[cls] = found;
}
console.log(JSON.stringify(results));
```
This technique works for verifying any CSS classes without needing data to trigger rendering.

## Data Dependencies
- **Leads data** comes from `projects` + `contacts` tables in Supabase (populated by GitHub Actions scraper every 6 hours)
- **TG Signals data** comes from `tg_signals` table (populated by TG parser workflow daily at 09:00 UTC — requires Telegram credentials)
- **Outreach Feed** comes from `outreach_logs` table (populated by auto_outreach.py)

## Known Gotchas
- TG Signals page might show empty state if the `tg_signals` table doesn't exist yet in Supabase (user needs to run the schema SQL) or if the parser hasn't been configured
- The dashboard has no authentication — anyone with the URL can view data
- Vercel preview deploys use the same Supabase instance as production (env vars are shared)
- The `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` are baked into the frontend build
- If Supabase returns errors, the dashboard silently shows empty states (check browser console for errors)
- Filter buttons work client-side — if data isn't loading, filters won't change anything
- Contact link buttons on TG Signal cards won't render without real data — verify CSS classes exist as a proxy test
- The TG parser GitHub Actions workflow might fail if secrets are added to "Environment secrets" instead of "Repository secrets" — check workflow logs for empty variable values

## Testing Without Data
When the TG parser hasn't been set up:
- You CAN test: tab navigation, empty state rendering, Leads page functionality, filters, CSS class deployment
- You CANNOT test: signal cards, contact link buttons, type/channel filters, "Add to Leads" flow, relevance scores
- Do NOT try to insert test data without Supabase credentials
- Use CSS class verification (see section 4) as a proxy for visual testing

## Browser Console Checks
Always check the browser console (`computer` tool with `action=console`) for:
- Supabase connection errors
- JavaScript runtime errors
- Failed network requests

To read console logs, call console with empty content first. Logs from your own scripts appear separately.

## Devin Secrets Needed
None required for read-only UI testing. The dashboard uses public Supabase anon key embedded in the build.

For full integration testing (inserting test signals), you would need:
- `SUPABASE_URL` — Supabase project URL
- `SUPABASE_SERVICE_KEY` — Service role key for direct DB writes
