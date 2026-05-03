# TTM Lead Gen

Automated lead generation and outreach pipeline for [Tothemoon](https://tothemoon.agency) — a crypto exchange listing agency.

## What It Does

Finds crypto projects → enriches contacts (BD, Founders) → sends personalized cold emails → tracks replies → manages follow-ups. Full autopilot with a dashboard for manual control.

**Problem it solves:** Manual BD outreach doesn't scale. This pipeline processes hundreds of projects daily, finds decision-makers, generates AI-personalized icebreakers, and runs multi-stage email campaigns automatically.

## Architecture

| Layer | Tech | Purpose |
|---|---|---|
| Dashboard | React + Vite on Vercel | Pipeline management, Smart Reply, CSV export |
| API | Vercel Serverless Functions | AI reply generation, GitHub Actions trigger, inbound webhook |
| Workers | Python scripts | Scraping, contact enrichment, outreach |
| Scheduler | GitHub Actions | Runs workers every 6h (leads) + daily (outreach) |
| Database | Supabase (Postgres) | Single source of truth for all data |

### Key Features
- **Lead discovery:** CoinGecko (live), ICO Drops (upcoming pre-launch tokens)
- **TG Signal Parser:** Monitors crypto Telegram channels, AI-classifies posts (TGE/listing, activity, long-term), surfaces actionable signals
- **Contact enrichment:** Email, Twitter/X, LinkedIn, Telegram via Serper.dev search
- **AI icebreakers:** Gemini generates personalized opening lines per project
- **Multi-stage outreach:** Cold → Follow-up 1 (4d) → Follow-up 2 (10d) → Offer
- **Inbound tracking:** Resend webhook captures replies, auto-updates project status
- **Dashboard refresh:** Triggers GitHub Actions workflow from UI

## Data Model

Defined in `schema.sql` — apply via Supabase SQL Editor.

- **projects** — scraped crypto projects (name, ticker, chain, mcap, status, upcoming metadata)
- **contacts** — enriched contacts per project (email, twitter, telegram, linkedin, role)
- **outreach_logs** — sent emails and inbound replies with timestamps
- **tg_signals** — classified signals from Telegram channels (TGE, activity, long-term)

## Local Setup

### Python Workers

```bash
cp .env.example .env   # fill in your keys
pip install -r requirements.txt
python pipeline.py             # scrape + enrich + brief
python pipeline.py --outreach  # + send emails
```

### Dashboard

```bash
cd dashboard
cp .env.example .env   # VITE_SUPABASE_URL, VITE_SUPABASE_KEY
npm install && npm run dev
```

## Environment Variables

### Root `.env` (Python workers + GitHub Actions)

| Variable | Required | Purpose |
|---|---|---|
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_KEY` | Yes | Supabase anon/service key |
| `SERPER_API_KEY` | Yes | Serper.dev Google Search (contact enrichment) |
| `GEMINI_API_KEY` | Yes | Google Gemini (AI icebreakers + TG signal classification) |
| `RESEND_API_KEY` | Yes | Resend (email sending) |
| `CG_API_KEY` | No | CoinGecko API (removes rate limit) |
| `TELEGRAM_API_ID` | For TG parser | From https://my.telegram.org |
| `TELEGRAM_API_HASH` | For TG parser | From https://my.telegram.org |
| `TELEGRAM_SESSION` | For TG parser | Generated via `python tg_auth.py` |

### `dashboard/.env` (Frontend)

| Variable | Required | Purpose |
|---|---|---|
| `VITE_SUPABASE_URL` | Yes | Supabase project URL (client-safe) |
| `VITE_SUPABASE_KEY` | Yes | Supabase anon key (client-safe) |
| `VITE_API_SECRET` | No | Auth token for API endpoints (must match Vercel `API_SECRET`) |

### Vercel Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `VITE_SUPABASE_URL` | Yes | Supabase URL |
| `VITE_SUPABASE_KEY` | Yes | Supabase anon key |
| `GEMINI_API_KEY` | Yes | For `/api/generate-reply` |
| `GITHUB_TOKEN` | Yes | PAT with `repo` + `workflow` scopes |
| `GITHUB_REPO` | Yes | e.g. `owner/repo` |
| `RESEND_WEBHOOK_SECRET` | Yes | Validates `/api/inbound` webhook |
| `API_SECRET` | Yes | Protects all API endpoints (endpoints return 500 if unset) |

### GitHub Actions Secrets

`SUPABASE_URL`, `SUPABASE_KEY`, `SERPER_API_KEY`, `CG_API_KEY`, `GEMINI_API_KEY`, `RESEND_API_KEY`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION`

### GitHub Actions Variables

| Variable | Purpose |
|---|---|
| `TG_CHANNELS` | Comma-separated channel usernames for TG parser (e.g. `crypto_news,ton_updates`) |

## Vercel API Endpoints

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| `/api/generate-reply` | POST | `API_SECRET` | Generates AI icebreaker for a project |
| `/api/trigger-refresh` | POST | `API_SECRET` | Triggers lead-refresh GitHub Actions workflow |
| `/api/check-refresh-status` | GET | `API_SECRET` | Polls workflow run status |
| `/api/inbound` | POST | `RESEND_WEBHOOK_SECRET` | Receives email reply webhooks from Resend |

## Enricher Modes

```bash
# Full mode — all platforms
python -c "import enricher; enricher.run(limit=30, email_only=False)"

# Email-only — optimized for outreach (mcap > $1M, no email yet)
python -c "import enricher; enricher.run(limit=30, email_only=True)"
```

## GitHub Actions Workflows

### Lead Refresh (`.github/workflows/lead-refresh.yml`)
- Schedule: every 6 hours
- Manual dispatch: `mode` (full/email_only), `enrich_limit` (30/50/100)

### Outreach (`.github/workflows/outreach.yml`)
- Manual dispatch (schedule disabled by default)
- Runs `auto_outreach.py` → Stage 1 + follow-ups

### TG Signal Parser (`.github/workflows/tg-parse.yml`)
- Schedule: every 2 hours
- Parses configured Telegram channels via Telethon
- AI-classifies posts with Gemini (TGE/listing, activity, long-term, noise)
- Stores signals in `tg_signals` table
- Setup: `python tg_auth.py` (one-time), add secrets + `TG_CHANNELS` variable

## Operational Model

1. **Lead Refresh** runs every 6h via GitHub Actions
2. **TG Signal Parser** runs every 2h — monitors crypto channels, AI-classifies signals
3. **Dashboard** on Vercel shows live pipeline state + TG Signals tab
4. **Email autopilot** via `auto_outreach.py` (Stage 1 → Follow-ups)
5. **Manual outreach** (X / Telegram) through dashboard
6. **Smart Reply** generated per project via Gemini
7. **Inbound replies** tracked automatically via Resend webhook

## Security Notes

- Never commit `.env` files — all are in `.gitignore`
- API endpoints require `API_SECRET` Bearer token
- Inbound webhook uses timing-safe secret comparison
- Enricher has SSRF protection (blocks private IPs, metadata endpoints)
- Email content is HTML-sanitized before sending
- CSV export is protected against formula injection
- GitHub Actions pinned to commit SHAs
- Dependencies have upper-bound version pins
