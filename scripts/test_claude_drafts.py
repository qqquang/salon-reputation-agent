#!/usr/bin/env python3
"""
test_claude_drafts.py — Preview Claude Sonnet draft replies for 5 real reviews.
Reads from Supabase, calls Claude, prints results. Writes NOTHING back to DB.

Usage:
  python3 scripts/test_claude_drafts.py
  python3 scripts/test_claude_drafts.py --count 10   # test more reviews
  python3 scripts/test_claude_drafts.py --low         # only show low-rated reviews
"""

import argparse
import os
import sys
from pathlib import Path

import anthropic
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

DRAFT_PROMPT = """You are the owner of {salon_name}, a neighborhood nail studio. Reply to this Google review as yourself — genuine, casual, and human. Keep it brief (2-3 sentences). Don't use marketing buzzwords or forced nail puns.

Reviewer: {author}
Review: "{text}"
Tone: {tone}

Write only the reply text, nothing else."""


def fetch_reviews(count: int, low_only: bool) -> list[dict]:
    url = f"{SUPABASE_URL}/rest/v1/reviews"
    params = {
        "select": "review_id,original_text,author_name,salon_name,rating,sentiment_score,draft_response",
        "order": "review_date.desc",
        "limit": str(count * 3),  # fetch extra so we can filter
    }
    if low_only:
        params["rating"] = "lte.3"

    r = requests.get(url, headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }, params=params)
    r.raise_for_status()
    return r.json()[:count]


def generate_draft(review: dict, client: anthropic.Anthropic) -> str:
    sentiment = review.get("sentiment_score") or 5
    tone = "warm and celebratory" if sentiment >= 7 else "empathetic and calm"
    prompt = DRAFT_PROMPT.format(
        salon_name=review.get("salon_name") or "Mi Nail Belleville",
        author=review.get("author_name") or "the reviewer",
        text=review.get("original_text") or "(no text — rating only)",
        tone=tone,
    )
    msg = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def stars(rating) -> str:
    r = int(rating or 0)
    return "★" * r + "☆" * (5 - r)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5, help="Number of reviews to test")
    parser.add_argument("--low", action="store_true", help="Only show reviews rated 3 stars or below")
    args = parser.parse_args()

    missing = [v for v in ("SUPABASE_KEY", "ANTHROPIC_API_KEY") if not os.environ.get(v)]
    if missing:
        print(f"❌  Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    print(f"Fetching {args.count} reviews from Supabase...")
    reviews = fetch_reviews(args.count, args.low)
    if not reviews:
        print("No reviews found.")
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    print(f"\n{'='*70}")
    print(f"  CLAUDE SONNET DRAFT TEST — {len(reviews)} reviews  (nothing saved to DB)")
    print(f"{'='*70}\n")

    for i, review in enumerate(reviews, 1):
        rating = review.get("rating", 0)
        author = review.get("author_name") or "Anonymous"
        text = review.get("original_text") or "(no written review)"
        existing = review.get("draft_response") or "(none)"

        print(f"[{i}/{len(reviews)}]  {stars(rating)}  {author}")
        print(f"  Review : {text[:120]}{'...' if len(text) > 120 else ''}")
        print(f"  Old    : {existing[:120]}{'...' if len(existing) > 120 else ''}")

        try:
            new_draft = generate_draft(review, client)
            print(f"  Claude : {new_draft}")
        except Exception as e:
            print(f"  Claude : ❌ ERROR — {e}")

        print()

    print("✅  Done — nothing was written to the database.")


if __name__ == "__main__":
    main()
