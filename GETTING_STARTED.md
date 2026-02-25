# Getting Started

## 1) Prerequisites

- Python 3.9+
- A terminal open in this project directory

## 2) Install dependencies

```bash
python3 -m pip install -r requirements.txt
```

## 3) Configure environment

Create a `.env` file based on `.env.example`.

```bash
cp .env.example .env
```

Optional personalization:
- Edit `config/brand_context.json` to define your salon voice, services, differentiators, and phrases to avoid in AI replies.

### Minimum variables for local offline testing

```env
DRY_RUN=true
SALON_CID=dry-test
DRY_RUN_REVIEWS_FILE=scripts/data/test_reviews.json
```

## 4) Run in offline mode (no paid API calls)

This mode does not call DataForSEO, OpenAI, or Supabase.

```bash
python3 src/main.py --once
```

Expected behavior:
- Reviews are loaded from `DRY_RUN_REVIEWS_FILE`
- AI output is simulated locally
- Database writes are printed as `[DRY_RUN] Would insert ...`

## 5) Run in production mode

Set in `.env`:

```env
DRY_RUN=false
DATAFORSEO_LOGIN=...
DATAFORSEO_PASSWORD=...
SUPABASE_URL=...
SUPABASE_KEY=...
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini
```

Then choose one target mode:
- `SALON_CID=<google-maps-cid>` for one salon
- or `SEARCH_QUERY=<query>` for discovery mode

Run once:

```bash
python3 src/main.py --once
```

Run as daemon:

```bash
python3 src/main.py
```

## 6) Useful scripts

- Router test with sample reviews:
  - `python3 scripts/test_router.py`
- OpenAI connectivity check:
  - `python3 scripts/test_conn.py`
- Reprocess existing DB records:
  - `python3 scripts/reprocess_db.py`
  - `python3 scripts/reprocess_recent.py`
- Cleanup script:
  - `python3 scripts/cleanup_reviews.py`

## 7) Troubleshooting

- `ModuleNotFoundError`: run `python3 -m pip install -r requirements.txt`
- No reviews found in production mode:
  - verify `SALON_CID` or `SEARCH_QUERY`
  - verify DataForSEO credentials
- Supabase errors:
  - verify `SUPABASE_URL` and `SUPABASE_KEY`
- OpenAI errors:
  - verify `OPENAI_API_KEY`

## 8) Daily Automation on Mac mini (launchd)

Install daily run at 09:00 local time:

```bash
./scripts/install_launchd_daily.sh
```

Install daily run at a custom time (hour minute):

```bash
./scripts/install_launchd_daily.sh 8 30
```

Remove the scheduled job:

```bash
./scripts/uninstall_launchd_daily.sh
```
