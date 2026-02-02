import time
import os
import sys

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# imports configuration variables (like SALON_CID, GEMINI_API_KEY, etc.)
from config import settings
from src.db.supabase_client import db
from src.ingestion.dataforseo import DataForSEOClient

# Configuration
CHECK_INTERVAL = 3600  # 1 hour

class SimpleIngestionAgent:
    def __init__(self):
        print("Initializing Simple Ingestion Agent...")
        self.dfs_client = DataForSEOClient()

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

        # 1. Discovery Mode (Search Query)
        if settings.SEARCH_QUERY:
            print(f"Running Discovery: '{settings.SEARCH_QUERY}'")
            businesses = self.dfs_client.search_businesses(settings.SEARCH_QUERY)
            print(f"Found {len(businesses)} businesses.")
            for biz in businesses:
                cid = biz.get('cid')
                title = biz.get('title')
                if cid:
                    target_cids.append((cid, title))
                    print(f" - Found: {title} ({cid})")
        
        # 2. Targeted Mode (Single CID)
        elif settings.SALON_CID:
             target_cids.append((settings.SALON_CID, "Unknown Salon"))
        
        else:
            print("Error: No SEARCH_QUERY or SALON_CID set.")
            return

        # 3. Ingest All Targets
        for cid, salon_name in target_cids:
            self.process_cid(cid, salon_name)

    def process_cid(self, cid, salon_name):
        print(f"Fetching reviews for {salon_name} ({cid})...")
        reviews = self.dfs_client.fetch_reviews(cid, depth=700)
        print(f"Found {len(reviews)} reviews.")

        for review in reviews:
            review_id = review.get('id_review') or review.get('review_id')
            if not review_id:
                continue

            if db.review_exists(review_id):
                # print(f"Skipping existing review {review_id}")
                continue
            
            print(f"New review found: {review_id}")
            
            # Simplified Record - No AI Analysis
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
                "status": "INGESTED", # Simple status
                "created_at": "now()"
            }
            
            db.insert_review(review_record)

if __name__ == "__main__":
    agent = SimpleIngestionAgent()
    agent.run()
