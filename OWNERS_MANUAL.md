# CivicPulse Louisville — Owner's Manual

Center for Neighborhoods · centerforneighborhoods.org/civicpulse

---

## What is this?

CivicPulse automatically tracks Louisville Metro Council Appropriations Committee
meetings and publishes NDF/CIF spending data in plain English for residents.

Three parts:
1. **The website** (index.html) — what the public sees
2. **The scraper** (scraper/scrape.py) — pulls meeting data daily
3. **The automation** (.github/workflows/scrape.yml) — runs scraper every morning

---

## How it works

Every morning at 6am, GitHub's free servers:
1. Run the scraper automatically
2. Visit Louisville Metro's Swagit video platform
3. Download transcripts from recent Appropriations Committee meetings
4. Extract dollar amounts, districts, recipients, and votes
5. Save everything to data/meetings.json
6. The website reads that file and displays it to the public
7. If anything fails, an alert email goes to mikalf@centerforneighborhoods.org

No one needs to do anything. It just runs.

---

## One-time setup (do this once)

1. Create a GitHub account at github.com if you don't have one
2. Create a new repository: github.com/new — name it "civicpulse"
3. Upload all these files to that repository
4. In your web host's control panel, point /civicpulse to the repository
   (or use GitHub Pages — it's free and works automatically)
5. Set up failure alerts — see section below

---

## Setting up failure alerts

1. GitHub repo → Settings → Secrets and variables → Actions
2. Add: ALERT_EMAIL_USER = a Gmail address to send from
3. Add: ALERT_EMAIL_PASS = that Gmail's App Password
   (Google Account → Security → 2-Step Verification → App passwords)
4. Done

---

## Running the scraper manually

From GitHub (easiest — no technical knowledge needed):
1. Go to your GitHub repository
2. Click the Actions tab
3. Click "CivicPulse Daily Scraper" in the left sidebar
4. Click "Run workflow" → "Run workflow"
5. Wait 2 minutes — done

---

## When the scraper breaks

Step 1: GitHub repo → Actions tab → click the failed run → read the red error

Common errors:
- ConnectionError/Timeout → Network issue, wait and re-run tomorrow
- KeyError or NoneType → Louisville Metro changed their site, update scrape.py
- 403 Forbidden → Site blocking scraper, contact Louisville Metro for data access

Step 2: Paste the error message to Claude and ask for help fixing it.
Step 3: If still stuck, contact your technical maintainer.

---

## Costs

GitHub Actions (automation): Free
GitHub repository: Free
Web hosting (CFN existing): $0 extra
Total monthly: ~$0

Optional later:
- Claude API for AI summaries: ~$10-25/month
- Mailchimp email digest: Free up to 500 subscribers

---

## Contact

CFN: Mikal Forbush — mikalf@centerforneighborhoods.org — (502) 589-0343
Technical maintainer: [Name] — [email]
