
import sys
import os
import time

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import settings
from src.db.supabase_client import db
from src.processing.router import IntelligenceRouter

def reprocess_reviews():
    print("--- Reprocessing All Reviews ---")
    
    # 1. Fetch all reviews
    print("Fetching reviews from database...")
    try:
        query = db.client.table("reviews").select("*")
        
        if settings.SALON_CID:
            print(f"Filtering by Salon CID: {settings.SALON_CID}")
            query = query.eq("cid", settings.SALON_CID)
            
        response = query.order("created_at", desc=False).execute()
        reviews = response.data
        print(f"Found {len(reviews)} reviews.")
    except Exception as e:
        print(f"Error fetching reviews: {e}")
        return

    # 2. Initialize Router
    router = IntelligenceRouter()
    
    # 3. Process Loop
    for i, review in enumerate(reviews):
        review_id = review.get('review_id')
        author = review.get('author_name', 'Unknown')
        print(f"\n[{i+1}/{len(reviews)}] Processing {author} ({review_id})...")
        
        # reconstruct review_data expected by router
        review_data = {
            "review_id": review_id,
            "original_text": review.get('original_text'),
            "rating": review.get('rating'),
            "author_name": author,
            "salon_name": review.get('salon_name')
        }
        
        # Get Context
        history = db.get_recent_responses(limit=5)
        
        # Run Analysis
        try:
            analysis = router.process_review(review_data, history)
            
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
            print(f" - Updated: {analysis.get('draft_response')[:50]}...")
            
            # Sleep slightly to avoid rate limits if any
            time.sleep(1)
            
        except Exception as e:
            print(f" - Error updating: {e}")

    print("\n✅ Reprocessing Complete.")

if __name__ == "__main__":
    reprocess_reviews()
