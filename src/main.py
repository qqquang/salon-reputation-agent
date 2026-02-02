import time
import os
from config import settings
from src.db.supabase import db
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
        print("Checking for reviews...")
        if not settings.SALON_CID:
            print("Error: SALON_CID not set.")
            return

        reviews = self.dfs_client.fetch_reviews(settings.SALON_CID)
        print(f"Found {len(reviews)} reviews from source.")

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
                "author_name": review.get('reviewer_name', 'Anonymous'),
                "rating": review.get('rating_value', 0),
                "original_text": review.get('review_text', ''),
                "raw_data": review,
                "status": "INGESTED", # Simple status
                "created_at": "now()"
            }
            
            db.insert_review(review_record)

if __name__ == "__main__":
    agent = SimpleIngestionAgent()
    agent.run()
