
import sys
import os
import time

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import settings
from src.db.supabase_client import db
from src.processing.router import IntelligenceRouter

def append_history_context(history_context, review_id, review_data, draft_response, limit=20):
    if history_context is None:
        history_context = []
    if review_id:
        history_context = [item for item in history_context if item.get("review_id") != review_id]
    history_context.insert(0, {
        "review_id": review_id,
        "author_name": review_data.get("author_name"),
        "rating": review_data.get("rating"),
        "original_text": review_data.get("original_text"),
        "draft_response": draft_response,
    })
    return history_context[:limit]

def reprocess_recent():
    print("--- Reprocessing Recent Reviews ---")
    
    # 1. Fetch recent reviews
    print("Fetching last 20 reviews from database...")
    try:
        query = db.client.table("reviews").select("*").order("created_at", desc=True).limit(20)
        
        if settings.SALON_CID:
            print(f"Filtering by Salon CID: {settings.SALON_CID}")
            query = query.eq("cid", settings.SALON_CID)
            
        response = query.execute()
        reviews = response.data
        print(f"Found {len(reviews)} reviews.")
    except Exception as e:
        print(f"Error fetching reviews: {e}")
        return

    # 2. Initialize Router
    router = IntelligenceRouter()
    # Seed context once and keep it updated in-memory during this run.
    history_context = db.get_recent_review_context(limit=20)
    print(f"Loaded {len(history_context)} recent review/response context records.")
    
    # 3. Process Loop
    for i, review in enumerate(reviews):
        review_id = review.get('review_id')
        author = review.get('author_name', 'Unknown')
        print(f"\n[{i+1}/{len(reviews)}] Processing {author} ({review_id})...")
        print(f" - Original Text: {review.get('original_text')}")
        
        # reconstruct review_data expected by router
        review_data = {
            "review_id": review_id,
            "original_text": review.get('original_text') or "",  # Handle None
            "rating": review.get('rating'),
            "author_name": author,
            "salon_name": review.get('salon_name')
        }
        
        # Run Analysis
        try:
            analysis = router.process_review(review_data, history_context)
            
            if not analysis:
                print(" - Failed to analyze.")
                continue

            # Update Payload
            update_payload = {
                "sentiment_score": analysis.get('scout', {}).get('sentiment_score'),
                "risk_flag": analysis.get('scout', {}).get('risk_flag', False),
                "category": analysis.get('scout', {}).get('category'),
                "vietnamese_summary": analysis.get('vietnamese_summary'),
                "draft_response": analysis.get('draft_response'),
                "analysis_json": analysis,
                "status": "ANALYZED",
                "updated_at": "now()"
            }
            
            # Save to DB
            db.client.table("reviews").update(update_payload).eq("review_id", review_id).execute()
            history_context = append_history_context(
                history_context,
                review_id,
                review_data,
                analysis.get('draft_response'),
                limit=20
            )
            print(f" - Updated: {analysis.get('draft_response')[:50]}...")
            
            # Sleep slightly to avoid rate limits if any
            time.sleep(1)
            
        except Exception as e:
            print(f" - Error updating: {e}")

    print("\n✅ Reprocess Recent Complete.")

if __name__ == "__main__":
    reprocess_recent()
