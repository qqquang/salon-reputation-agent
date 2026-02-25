# Salon Reputation Agent

Automates Google review ingestion, AI analysis, and response drafting for salon reputation management.

Reviews are fetched from Google via DataForSEO, analyzed by GPT-4o-mini (text) and Gemini 2.0 Flash (customer photos), and draft responses are saved to Supabase.

## How It Works

```
DataForSEO → fetch reviews
     ↓
Gemini 2.0 Flash → analyze customer photos (if any)
     ↓
GPT-4o-mini → Scout (sentiment, risk, category)
     ↓
GPT-4o-mini → Translate summary to Vietnamese (for owner)
     ↓
GPT-4o-mini → Draft response (anti-repetition, brand voice)
     ↓
Supabase → save review + draft
```

## Project Structure

```
salon-reputation-agent/
├── src/
│   ├── main.py                  # Orchestration entrypoint
│   ├── processing/router.py     # AI pipeline (Scout → Translate → Draft)
│   ├── ingestion/dataforseo.py  # Review fetching from DataForSEO
│   └── db/supabase_client.py    # Database client + helpers
├── config/
│   ├── settings.py              # Env var loading
│   ├── prompts.json             # AI prompt templates
│   └── brand_context.json       # Salon voice, tone, services
├── scripts/
│   ├── reprocess_recent.py      # Reprocess last N reviews
│   ├── reprocess_db.py          # Reprocess all DB records
│   ├── cleanup_reviews.py       # Delete error rows from DB
│   ├── install_launchd_daily.sh # Schedule daily run (macOS)
│   └── uninstall_launchd_daily.sh
├── tests/                       # pytest test suite (109 tests)
└── requirements.txt
```

## Quick Start

Full setup guide: [`GETTING_STARTED.md`](GETTING_STARTED.md)

### 1. Install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Minimum `.env` for offline testing:

```env
DRY_RUN=true
SALON_CID=dry-test
DRY_RUN_REVIEWS_FILE=scripts/data/test_reviews.json
```

Full `.env` for production:

```env
DRY_RUN=false
DATAFORSEO_LOGIN=your@email.com
DATAFORSEO_PASSWORD=your_password
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_key
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...
SALON_CID=<google-maps-cid>
```

### 3. Run

```bash
# Run once
python3 src/main.py --once

# Run continuously (daemon mode)
python3 src/main.py
```

## Daily Automation (macOS launchd)

```bash
# Install at default time (09:00)
./scripts/install_launchd_daily.sh

# Install at custom time (e.g. 11:00 AM)
./scripts/install_launchd_daily.sh 11 0

# Remove the scheduled job
./scripts/uninstall_launchd_daily.sh
```

## Configuration

### Brand Voice (`config/brand_context.json`)

Customize the AI response style for your salon:

```json
{
  "name": "Mi Nail",
  "identity": "Premium nail salon known for quality and care",
  "tone": ["warm", "professional", "appreciative"],
  "services": ["manicure", "pedicure", "nail art", "gel"],
  "differentiators": ["organic products", "skilled technicians"],
  "avoid_phrases": ["no problem", "not an issue"]
}
```

### Prompts (`config/prompts.json`)

AI prompt templates for each pipeline step: `scout`, `translate`, `consult`, `draft`.

## Scripts

| Script | Purpose |
|---|---|
| `scripts/reprocess_recent.py --limit N` | Re-run AI pipeline on last N reviews (default 10) |
| `scripts/reprocess_db.py` | Re-run AI pipeline on all DB records |
| `scripts/cleanup_reviews.py` | Delete error-status rows from the database |
| `scripts/test_router.py` | Manual router test with sample reviews |
| `scripts/test_conn.py` | Verify OpenAI/Supabase connectivity |

## Tests

```bash
# Run all tests
./venv/bin/python -m pytest tests/

# With coverage report
./venv/bin/python -m pytest tests/ --cov=src --cov-report=term-missing
```

109 tests, 63% coverage across `router.py`, `dataforseo.py`, and `supabase_client.py`.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | OpenAI API key (GPT-4o-mini for text) |
| `GEMINI_API_KEY` | Recommended | Google Gemini key (image analysis) |
| `DATAFORSEO_LOGIN` | Yes (prod) | DataForSEO account email |
| `DATAFORSEO_PASSWORD` | Yes (prod) | DataForSEO account password |
| `SUPABASE_URL` | Yes (prod) | Supabase project URL |
| `SUPABASE_KEY` | Yes (prod) | Supabase anon/service key |
| `SALON_CID` | Yes | Google Maps CID for the salon |
| `SALON_NAME` | No | Display name fallback (default: `N/A`) |
| `OPENAI_MODEL` | No | OpenAI model (default: `gpt-4o-mini`) |
| `VISION_MODEL` | No | Gemini model (default: `gemini-2.0-flash`) |
| `DRY_RUN` | No | Skip all API/DB calls (default: `false`) |
| `DATAFORSEO_USE_SANDBOX` | No | Use DataForSEO sandbox (default: `false`) |

## Troubleshooting

- **`ModuleNotFoundError`** — run `pip install -r requirements.txt` inside your venv
- **`OPENAI_API_KEY is not set`** — add the key to your `.env` file
- **No reviews found** — verify `SALON_CID` and DataForSEO credentials
- **Supabase errors** — verify `SUPABASE_URL` and `SUPABASE_KEY`
- **Image analysis skipped** — add `GEMINI_API_KEY` to `.env`
- **SSL errors on macOS** — ensure you're using the `requests` library (already the default)
