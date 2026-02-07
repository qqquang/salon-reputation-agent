import time
import os
import sys

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# imports configuration variables (like SALON_CID, GEMINI_API_KEY, etc.)
from config import settings
from src.db.supabase_client import db
from src.ingestion.dataforseo import DataForSEOClient
from src.processing.router import IntelligenceRouter

# Configuration
CHECK_INTERVAL = 3600  # 1 hour

class SimpleIngestionAgent:
    def __init__(self):
        print("Initializing Simple Ingestion Agent...")
        self.dfs_client = DataForSEOClient()
        self.router = IntelligenceRouter()

    def run(self):
        print("Ingestion Agent Started. Press Ctrl+C to stop.")
        while True:
            try:
                self.ingest_reviews()
                print(f"Sleeping for {CHECK_INTERVAL} seconds...")
                time.sleep(CHECK_INTERVAL)
            except KeyboardInterrupt:
                print("Stopping...")
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(60)

    def ingest_reviews(self):
        target_cids = []

        # 1. Targeted Mode (Single CID)
        if settings.SALON_CID:
             target_cids.append((settings.SALON_CID, "Unknown Salon"))
        # 2. Discovery Mode (Search Query)
        elif settings.SEARCH_QUERY:
            print(f"Running Discovery: '{settings.SEARCH_QUERY}'")
            businesses = self.dfs_client.search_businesses(settings.SEARCH_QUERY)
            print(f"Found {len(businesses)} businesses.")
            for biz in businesses:
                cid = biz.get('cid')
                title = biz.get('title')
                if cid:
                    target_cids.append((cid, title))
                    print(f" - Found: {title} ({cid})")
        
        else:
            print("Error: No SEARCH_QUERY or SALON_CID set.")
            return

        # 3. Ingest All Targets
        for cid, salon_name in target_cids:
            self.process_cid(cid, salon_name)

    def process_cid(self, cid, salon_name):
        print(f"Fetching reviews for {salon_name} ({cid})...")
        reviews, fetched_name = self.dfs_client.fetch_reviews(cid, depth=700)
        
        # Update name if available and we are using default/fallback
        if fetched_name:
            if salon_name in ["Unknown Salon", "My Salon", "N/A"] or not salon_name:
                print(f"Auto-detected Salon Name: {fetched_name}")
                salon_name = fetched_name
                
        print(f"Found {len(reviews)} reviews for {salon_name}.")

        for review in reviews:
            review_id = review.get('id_review') or review.get('review_id')
            if not review_id:
                continue

            if db.review_exists(review_id):
                # print(f"Skipping existing review {review_id}")
                continue
            
            print(f"New review found: {review_id}")
            
            # 1. Create Base Record
            review_record = {
                "review_id": review_id,
                "cid": cid,
                "salon_name": salon_name,
                "author_name": review.get('profile_name', 'Anonymous'),
                "rating": review.get('rating', {}).get('value', 0),
                "original_text": review.get('review_text', ''),
                "owner_response": review.get('owner_answer', ''),
                "review_url": review.get('review_url', ''),
                "review_date": review.get('timestamp'), # Accurate review time
                "profile_image_url": review.get('profile_image_url', ''),
                "author_review_count": review.get('reviews_count', 0),
                "raw_data": review,
                "created_at": "now()"
            }

            # 2. AI Analysis (The Brain)
            print(f" - Analyzing review...")
            # Fetch recent history for context
            history = db.get_recent_responses(limit=5)
            analysis = self.router.process_review(review_record, history)
            
            # 3. Merge Analysis
            review_record.update({
                "sentiment_score": analysis.get('scout', {}).get('sentiment_score'),
                "risk_flag": analysis.get('scout', {}).get('risk_flag', False),
                "category": analysis.get('scout', {}).get('category'),
                "vietnamese_summary": analysis.get('vietnamese_summary'),
                "draft_response": analysis.get('draft_response'),
                "analysis_json": analysis, # Store full trace
                "status": "ANALYZED"
            })
            
            # 4. Save to DB
            db.insert_review(review_record)
            print(f" - Saved.")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Salon Reputation Agent")
    parser.add_argument("--once", action="store_true", help="Run a single ingestion cycle and exit.")
    args = parser.parse_args()

    agent = SimpleIngestionAgent()
    
    if args.once:
        print("Running in SINGLE-SHOT mode...")
        agent.ingest_reviews()
        print("Cycle complete. Exiting.")
    else:
        print("Running in DAEMON mode (Press Ctrl+C to stop)...")
        agent.run()
