# Salon Reputation Agent

Automates Google review ingestion, AI analysis, and response drafting for salon reputation workflows.

## Quick Start

Full setup guide:
- [`GETTING_STARTED.md`](GETTING_STARTED.md)

### Offline test mode (no paid API calls)

Set in `.env`:

```env
DRY_RUN=true
SALON_CID=dry-test
DRY_RUN_REVIEWS_FILE=scripts/data/test_reviews.json
```

Run:

```bash
python3 src/main.py --once
```

### Production mode

Set in `.env`:

```env
DRY_RUN=false
DATAFORSEO_LOGIN=...
DATAFORSEO_PASSWORD=...
SUPABASE_URL=...
SUPABASE_KEY=...
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5-mini
```

Run once:

```bash
python3 src/main.py --once
```

Run continuously:

```bash
python3 src/main.py
```

## Daily Auto Run (macOS launchd)

Install a daily job (default `09:00` local time):

```bash
./scripts/install_launchd_daily.sh
```

Install at a custom time (`hour minute`):

```bash
./scripts/install_launchd_daily.sh 8 30
```

Remove the daily job:

```bash
./scripts/uninstall_launchd_daily.sh
```
