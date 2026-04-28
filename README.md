# TTM Lead Gen

Internal lead generation and outreach pipeline for Tothemoon.

The system combines:
- `Supabase` as the source of truth
- `React + Vite` dashboard for pipeline management
- `Vercel Functions` for Smart Reply generation with Gemini
- `Python workers` for scraping, enrichment, briefing, and outreach
- `GitHub Actions` for scheduled background runs

## Architecture

### Dashboard
- Path: `dashboard/`
- Stack: `React`, `Vite`, `@supabase/supabase-js`
- Purpose: manage leads, filter pipeline, log outreach, generate Smart Reply

### Background Workers
- `scraper.py`: pulls new crypto projects into Supabase
- `scraper_upcoming.py`: pulls pre-launch token sales from ICO Drops
- `enricher.py`: finds contacts, prioritizes email and decision makers
- `briefing.py`: prints a daily pipeline briefing
- `auto_outreach.py`: sends Stage 1 and follow-up emails
- `pipeline.py`: runs scraper + enricher + briefing together

### Scheduled Automation
- `.github/workflows/lead-refresh.yml`
  - runs every 6 hours
  - supports manual run with `email_only` or `full` mode
  - writes a summary to GitHub Actions
- `.github/workflows/outreach.yml`
  - runs the automated outreach cycle
  - writes a summary to GitHub Actions

## Data Model

Main tables are defined in `schema.sql`:
- `projects`
- `contacts`
- `outreach_logs`

If you added new fields such as `is_upcoming`, `launch_date`, or `launchpad`, apply `schema.sql` in the Supabase SQL editor so the dashboard and workers can store full upcoming-sale metadata.

Supabase is the shared backend for both the dashboard and background jobs.

## Local Setup

### 1. Python workers

Create `.env` in the repository root.

Required values:

```env
SUPABASE_URL=
SUPABASE_KEY=
SERPER_API_KEY=
GEMINI_API_KEY=
RESEND_API_KEY=
CG_API_KEY=
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the full local pipeline:

```bash
py pipeline.py
```

Run pipeline with outreach:

```bash
py pipeline.py --outreach
```

Useful one-off commands:

```bash
py scraper.py
py scraper_upcoming.py
py -c "import enricher; enricher.run(limit=30)"
py -c "import enricher; enricher.run(limit=30, email_only=True)"
py auto_outreach.py
py briefing.py
```

### 2. Dashboard

Create `dashboard/.env`:

```env
VITE_SUPABASE_URL=
VITE_SUPABASE_KEY=
```

Install frontend dependencies:

```bash
cd dashboard
npm install
```

Run locally:

```bash
npm run dev
```

Build locally:

```bash
npm run build
```

## Enricher Modes

`enricher.py` supports two practical modes:

### Full mode

```bash
py -c "import enricher; enricher.run(limit=30, email_only=False)"
```

Finds:
- `Email`
- `LinkedIn`
- `X / Twitter`
- `Telegram`

### Email-only mode

```bash
py -c "import enricher; enricher.run(limit=30, email_only=True)"
```

Optimized for auto outreach. Prioritizes:
- projects with `mcap > $1M`
- projects without `Email`
- docs / media-kit / partnerships / press pages

## Vercel Deployment

Deploy `dashboard/` to Vercel.

Set these environment variables in Vercel:

```env
VITE_SUPABASE_URL=
VITE_SUPABASE_KEY=
GEMINI_API_KEY=
GITHUB_TOKEN=<GitHub PAT with repo + workflow scopes>
GITHUB_REPO=iaqool/tothemoon
```

Notes:
- `GEMINI_API_KEY` is used by `dashboard/api/generate-reply.js`
- `GITHUB_TOKEN` and `GITHUB_REPO` are required for the "Refresh Leads" button in the dashboard to trigger GitHub Actions workflows
- client-side Supabase keys must be the frontend-safe keys you intend to expose

## GitHub Actions Setup

Repository secrets required for background workflows:

```env
SUPABASE_URL
SUPABASE_KEY
SERPER_API_KEY
CG_API_KEY
GEMINI_API_KEY
RESEND_API_KEY
```

### Lead Refresh

Workflow: `.github/workflows/lead-refresh.yml`

Manual options:
- `mode = email_only`
- `mode = full`
- `enrich_limit = 30/50/100`

Output:
- new emails found
- new founders found
- new BD / Listing contacts found
- priority leads summary

### Outreach Cycle

Workflow: `.github/workflows/outreach.yml`

Output:
- Stage 1 sent
- Follow-up 1 sent
- Follow-up 2 sent
- recent activity summary

## Current Operational Model

Recommended usage:

1. `Lead Refresh` runs every 6 hours in GitHub Actions
2. Dashboard on Vercel shows current pipeline state
3. Manual outreach is done through dashboard for `X / TG`
4. Email autopilot uses `auto_outreach.py`
5. Upcoming token sales are imported before CoinGecko listings hit the market
6. Smart Reply is generated via Vercel serverless function

## Notes

- Vercel is used for UI and fast AI endpoints, not long-running Python jobs
- GitHub Actions is used for scheduled scraping, enrichment, and outreach
- Supabase remains the single shared backend
- Do not print secrets in workflow logs
