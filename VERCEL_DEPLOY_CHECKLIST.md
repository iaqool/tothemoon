# Vercel Deployment Checklist — TTM Lead Gen Dashboard

**Target:** Deploy `dashboard/` folder to Vercel  
**Root Directory:** `dashboard/`  
**Framework:** Vite (React)

---

## Pre-Deployment: Local Validation

### Step 1: Verify Build
```bash
cd dashboard
npm install
npm run build
```

**Expected Output:**
```
✓ 72 modules transformed
✓ dist/index.html
✓ dist/assets/index-*.css
✓ dist/assets/index-*.js
✓ built in ~2s
```

**If build fails:** Fix errors before proceeding.

---

### Step 2: Test Locally
```bash
npm run dev
```

Open `http://localhost:5173` and verify:
- [ ] Dashboard loads without errors
- [ ] KPI cards display
- [ ] Project table renders
- [ ] Filters work
- [ ] Modal opens

**Note:** Some features require Supabase connection. Set `dashboard/.env`:
```env
VITE_SUPABASE_URL=your_supabase_url
VITE_SUPABASE_KEY=your_supabase_anon_key
```

---

## Vercel Setup

### Step 3: Create Vercel Project

**Option A: Via Vercel CLI**
```bash
npm install -g vercel
cd dashboard
vercel
```

**Option B: Via Vercel Dashboard**
1. Go to https://vercel.com/new
2. Import Git repository
3. **IMPORTANT:** Set Root Directory to `dashboard`
4. Framework Preset: Vite
5. Build Command: `npm run build`
6. Output Directory: `dist`

---

### Step 4: Configure Environment Variables

Go to **Project Settings → Environment Variables** and add:

#### Required for Dashboard
```
VITE_SUPABASE_URL = https://your-project.supabase.co
VITE_SUPABASE_KEY = your_supabase_anon_key
```

#### Required for Smart Reply API (`api/generate-reply.js`)
```
GEMINI_API_KEY = your_gemini_api_key
```

#### Required for Inbound Webhook (`api/inbound.js`)
```
SUPABASE_URL = https://your-project.supabase.co
SUPABASE_KEY = your_supabase_service_role_key
RESEND_WEBHOOK_SECRET = your_webhook_secret_token
```

**Security Notes:**
- Use **anon key** for `VITE_*` variables (client-side)
- Use **service role key** for `SUPABASE_KEY` (server-side API routes)
- Generate `RESEND_WEBHOOK_SECRET` with: `openssl rand -hex 32`

**Apply to:** Production, Preview, Development

---

### Step 5: Verify `vercel.json` Configuration

File: `dashboard/vercel.json`

```json
{
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "framework": "vite",
  "rewrites": [
    {
      "source": "/(.*)",
      "destination": "/index.html"
    }
  ]
}
```

**What this does:**
- `rewrites`: Enables SPA routing (all routes → index.html)
- `outputDirectory`: Tells Vercel where build artifacts are
- `framework`: Auto-detects Vite optimizations

**Status:** ✅ Already configured correctly.

---

### Step 6: Deploy

**Via CLI:**
```bash
cd dashboard
vercel --prod
```

**Via Git Push:**
1. Push to `main` branch
2. Vercel auto-deploys

**Expected Output:**
```
✅ Production: https://your-project.vercel.app
```

---

## Post-Deployment: Verification

### Step 7: Test Dashboard

Visit your Vercel URL and verify:
- [ ] Dashboard loads
- [ ] No console errors (F12 → Console)
- [ ] Projects load from Supabase
- [ ] KPI metrics display
- [ ] Outreach feed shows recent logs
- [ ] Smart Reply button works

**If data doesn't load:**
- Check browser console for CORS errors
- Verify `VITE_SUPABASE_URL` and `VITE_SUPABASE_KEY` in Vercel
- Check Supabase RLS policies allow anon key access

---

### Step 8: Test Smart Reply API

**Method 1: Via Dashboard**
1. Open a project modal
2. Click "🤖 Smart Reply"
3. Verify AI-generated text appears

**Method 2: Via cURL**
```bash
curl -X POST https://your-project.vercel.app/api/generate-reply \
  -H "Content-Type: application/json" \
  -d '{
    "name": "TestProject",
    "ticker": "TEST",
    "chain": "Solana",
    "mcap": 5000000
  }'
```

**Expected Response:**
```json
{
  "reply": "Hey! I saw TestProject ($TEST) is building on Solana..."
}
```

**If it fails:**
- Check Vercel logs: `vercel logs`
- Verify `GEMINI_API_KEY` is set
- Check API route exists: `dashboard/api/generate-reply.js`

---

### Step 9: Test Inbound Webhook

**IMPORTANT:** Before testing, apply the critical fix to `inbound.js` (see Step 10).

**Method 1: Via Resend Dashboard**
1. Go to Resend → Webhooks
2. Add webhook: `https://your-project.vercel.app/api/inbound`
3. Event: `email.received` or `email.replied`
4. Secret: Use the same value as `RESEND_WEBHOOK_SECRET`
5. Send test event

**Method 2: Via cURL**
```bash
curl -X POST https://your-project.vercel.app/api/inbound \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_webhook_secret" \
  -d '{
    "from": "founder@testproject.com",
    "text": "Thanks for reaching out! Let us schedule a call."
  }'
```

**Expected Response:**
```json
{
  "success": true,
  "matchedContacts": 1
}
```

**Verify in Supabase:**
1. Check `projects` table: status should be `replied`
2. Check `outreach_logs` table: new entry with `stage='Inbound Reply'`

**If webhook fails:**
- Check Vercel logs: `vercel logs --follow`
- Verify `SUPABASE_URL`, `SUPABASE_KEY`, `RESEND_WEBHOOK_SECRET`
- Ensure contact email exists in `contacts` table

---

## Critical Fixes (Apply Before Production)

### Step 10: Schema Migration for `raw_payload`

**Problem:** `inbound.js` references `raw_payload` column that needs to be added to `outreach_logs`.

**Solution: Apply Schema Update**

Run in Supabase SQL Editor:
```sql
ALTER TABLE outreach_logs ADD COLUMN IF NOT EXISTS raw_payload JSONB;
```

**Verification:** Column is already added to `schema.sql`:
```sql
-- In outreach_logs table definition
raw_payload JSONB

-- As ALTER statement
ALTER TABLE outreach_logs ADD COLUMN IF NOT EXISTS raw_payload JSONB;
```

**Note:** `inbound.js` keeps `raw_payload` insertion as designed.

---

### Step 11: Harden Webhook Authentication

Edit `dashboard/api/inbound.js` lines 24-34:

**Before:**
```javascript
if (RESEND_WEBHOOK_SECRET) {
    const authHeader = req.headers['authorization'];
    if (authHeader !== `Bearer ${RESEND_WEBHOOK_SECRET}`) {
        console.warn("[WARN] Invalid or missing Authorization header.");
    }
}
```

**After:**
```javascript
if (!RESEND_WEBHOOK_SECRET) {
    console.error("[ERROR] RESEND_WEBHOOK_SECRET not configured");
    return res.status(500).json({ error: 'Server misconfiguration' });
}

const authHeader = req.headers['authorization'];
if (authHeader !== `Bearer ${RESEND_WEBHOOK_SECRET}`) {
    console.error("[ERROR] Unauthorized webhook request");
    return res.status(401).json({ error: 'Unauthorized' });
}
```

---

### Step 12: Add Payload Validation

Edit `dashboard/api/inbound.js` after line 40:

**Add:**
```javascript
const emailData = payload.type && payload.data ? payload.data : payload;

// Add validation
if (!emailData || typeof emailData !== 'object') {
    return res.status(400).json({ error: 'Invalid payload structure' });
}
```

---

## Deployment Workflow

### For Future Updates

**Automatic Deployment (Recommended):**
1. Push changes to `main` branch
2. Vercel auto-deploys
3. Check deployment status: https://vercel.com/dashboard

**Manual Deployment:**
```bash
cd dashboard
vercel --prod
```

**Rollback if needed:**
```bash
vercel rollback
```

---

## Monitoring

### Vercel Logs
```bash
vercel logs --follow
```

**Or via Dashboard:**
https://vercel.com/your-project/logs

**Watch for:**
- Webhook authentication failures
- Supabase connection errors
- Gemini API rate limits

---

## Troubleshooting

### Dashboard doesn't load
- Check browser console for errors
- Verify `VITE_SUPABASE_URL` and `VITE_SUPABASE_KEY`
- Check Vercel build logs

### Smart Reply fails
- Verify `GEMINI_API_KEY` is set
- Check Vercel function logs
- Ensure API route is deployed: `/api/generate-reply`

### Webhook not working
- Verify `RESEND_WEBHOOK_SECRET` matches Resend config
- Check `Authorization` header format: `Bearer <secret>`
- Ensure contact email exists in database
- Check Vercel function logs for errors

### Environment variables not working
- Redeploy after adding new variables
- Check variable names (case-sensitive)
- Verify applied to correct environment (Production/Preview/Development)

---

## Security Checklist

Before going live:
- [ ] `RESEND_WEBHOOK_SECRET` is set and strong (32+ chars)
- [ ] Webhook authentication is enforced (Step 11 applied)
- [ ] Service role key is NOT exposed to client
- [ ] Anon key has proper RLS policies in Supabase
- [ ] `.env` files are in `.gitignore`
- [ ] No secrets in Git history

---

## Success Criteria

Your deployment is successful when:
- ✅ Dashboard loads at Vercel URL
- ✅ Projects display from Supabase
- ✅ Smart Reply generates AI text
- ✅ Webhook updates project status to `replied`
- ✅ No errors in Vercel logs
- ✅ GitHub Actions workflows run successfully

---

**Estimated Time:** 30-45 minutes (first deployment)

**Support:**
- Vercel Docs: https://vercel.com/docs
- Supabase Docs: https://supabase.com/docs
- GitHub Actions: https://docs.github.com/actions

---

**End of Deployment Checklist**
