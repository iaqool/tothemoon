# Tothemoon — BD Autopilot for Crypto Projects

Automated pipeline that finds new crypto projects, discovers decision-maker contacts, writes personalized cold emails with AI, and sends them with follow-ups — on full autopilot.

## What It Does

```
CoinGecko / ICO Drops
        |
   [ Scraper ]  ──  finds new projects (MCap > $100k, 12 chains)
        |
   [ Enricher ] ──  finds BD / Founder / Listing Manager contacts
        |               via Serper.dev search + website parsing
        |
  [ AI Generator ] ── writes personalized icebreaker (Gemini)
        |
   [ Sender ]   ──  sends cold email via Resend
        |
   [ Follow-ups ] ── auto follow-up at day 4 and day 10
        |
   [ Dashboard ]  ── Vercel app to view pipeline, manage leads,
                      log manual outreach (X / TG), generate Smart Reply
```

**Supported chains:** Solana, TON, Base, Ethereum, BNB Chain, Tron, Arbitrum, Polygon, Optimism, Injective, Stellar, Celo
**Priority chains** (auto-flagged): Solana, TON, Base

## What Runs Automatically

| What | When | How |
|------|------|-----|
| Scrape new projects (CoinGecko + ICO Drops) | Every 6 hours | GitHub Actions `lead-refresh.yml` |
| Enrich contacts (email, X, TG, LinkedIn) | Every 6 hours (after scrape) | GitHub Actions `lead-refresh.yml` |
| Send cold emails (Stage 1) | Daily at 08:30 UTC | GitHub Actions `outreach.yml` |
| Send follow-ups (day 4 + day 10) | Daily at 08:30 UTC | GitHub Actions `outreach.yml` |

**What you do manually:** review leads in dashboard, do X/TG outreach, handle replies, adjust priority.

## Quick Start

### 1. Set up Supabase

Create a project at [supabase.com](https://supabase.com). Run `schema.sql` in the SQL Editor.

### 2. Configure environment

Copy `.env.example` to `.env` and fill in your keys:

| Variable | Where to get | Used by |
|----------|-------------|---------|
| `SUPABASE_URL` | Supabase → Settings → API | Everything |
| `SUPABASE_KEY` | Supabase → Settings → API (anon key) | Everything |
| `SERPER_API_KEY` | [serper.dev](https://serper.dev) (free: 2500 req/mo) | Enricher |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) | AI icebreakers |
| `RESEND_API_KEY` | [resend.com](https://resend.com) | Email sending |
| `CG_API_KEY` | [CoinGecko](https://www.coingecko.com/en/api) (optional, demo works) | Scraper |
| `API_SECRET` | Generate yourself (`openssl rand -hex 32`) | API endpoint auth |

### 3. Run locally

```bash
pip install -r requirements.txt
python pipeline.py            # scrape + enrich + briefing
python pipeline.py --outreach # + send emails
```

Dashboard:
```bash
cd dashboard && npm install && npm run dev
# Open http://localhost:5173
```

## Deploy to Production

### Dashboard → Vercel

Deploy `dashboard/` directory. Set env vars:

```
VITE_SUPABASE_URL, VITE_SUPABASE_KEY, GEMINI_API_KEY, API_SECRET, VITE_API_SECRET
```

`VITE_API_SECRET` must equal `API_SECRET` — the dashboard uses it to authenticate API calls.

### Workers → GitHub Actions

Add these as repository secrets:

```
SUPABASE_URL, SUPABASE_KEY, SERPER_API_KEY, CG_API_KEY, GEMINI_API_KEY, RESEND_API_KEY
```

Workers run on schedule automatically. Manual trigger available in Actions tab.

### Email → Custom domain

Outreach requires a verified sending domain:
1. Buy a domain (e.g. `tothemoon.agency`)
2. Set up DNS records (SPF, DKIM, DMARC) in Resend
3. Update `SENDER_EMAIL` in `sender.py`
4. Uncomment `schedule` in `outreach.yml`

## Pipeline Components

| File | Purpose |
|------|---------|
| `scraper.py` | Pulls live projects from CoinGecko API |
| `scraper_upcoming.py` | Scrapes upcoming token sales from ICO Drops |
| `enricher.py` | Finds contacts via search + website parsing |
| `ai_generator.py` | Generates personalized email openers (Gemini) |
| `sender.py` | Sends emails via Resend API |
| `auto_outreach.py` | Orchestrates cold emails + follow-ups |
| `briefing.py` | Prints daily pipeline summary |
| `pipeline.py` | Runs scraper → enricher → briefing in sequence |
| `dashboard/` | React app for pipeline management |
| `dashboard/api/` | Vercel serverless functions (Smart Reply, workflow trigger) |

## Data Model

Three tables in Supabase (defined in `schema.sql`):

- **projects** — scraped crypto projects with chain, MCap, status, priority flag
- **contacts** — found people (email, X, TG, LinkedIn) linked to projects
- **outreach_logs** — sent emails and responses, linked to contacts

Project status flow: `not_contacted` → `contacted` → `replied` / `follow_up` / `no_response`

## Outreach Logic

- **Stage 1 (Cold):** AI-personalized email to best available contact (prefers Founder/BD)
- **Follow-up 1:** 4 days after Stage 1, if no reply
- **Follow-up 2:** 10 days after Stage 1, if still no reply
- Domain deduplication: won't email two tokens from same team in one run
- Daily limits configurable via `OUTREACH_DAILY_LIMIT` (default: 3)

## Troubleshooting

| Problem | Fix |
|---------|-----|
| CoinGecko blocks GitHub Actions IP | Pre-existing — scraper has `continue-on-error: true`, enricher still runs |
| Emails going to spam | Need verified custom domain with SPF/DKIM/DMARC |
| Dashboard shows no data | Check `VITE_SUPABASE_URL` and `VITE_SUPABASE_KEY` in Vercel env vars |
| "Refresh Leads" button fails | Set `GITHUB_TOKEN` and `GITHUB_REPO` in Vercel env vars |
| Enricher finds no emails | Normal for some projects — not every site exposes BD contacts |
| Smart Reply returns fallback | `GEMINI_API_KEY` not set or quota exceeded — fallback template is used |
