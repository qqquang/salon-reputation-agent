import time
import os
import datetime
from config import settings
from src.db.supabase import db
from src.ingestion.dataforseo import DataForSEOClient
from src.processing.router import IntelligenceRouter
from src.gatekeeper.twilio_bot import TwilioGatekeeper
from src.posting.google_api import GooglePoster

# Configuration
REVIEW_CHECK_INTERVAL = 3600  # 1 hour
SMS_CHECK_INTERVAL = 30       # 30 seconds
CONTEXT_IMAGE_PATH = os.path.join("images", "price_list.jpg")

class SalonAgent:
    def __init__(self):
        print("Initializing Salon Reputation Agent...")
        self.dfs_client = DataForSEOClient()
        self.router = IntelligenceRouter()
        self.gatekeeper = TwilioGatekeeper()
        self.poster = GooglePoster()
        self.last_review_check = 0

    def run(self):
        print("Agent Started. Press Ctrl+C to stop.")
        while True:
            try:
                current_time = time.time()
                
                # 1. Ingestion Cycle
                if current_time - self.last_review_check > REVIEW_CHECK_INTERVAL:
                    self.process_new_reviews()
                    self.last_review_check = current_time

                # 2. Approval Cycle
                self.process_approvals()

                # Sleep
                time.sleep(SMS_CHECK_INTERVAL)

            except KeyboardInterrupt:
                print("Agent stopping...")
                break
            except Exception as e:
                print(f"Unexpected Error in Main Loop: {e}")
                time.sleep(60)

    def process_new_reviews(self):
        print("Checking for new reviews...")
        if not settings.SALON_CID:
            print("Error: SALON_CID not set in settings.")
            return

        reviews = self.dfs_client.fetch_reviews(settings.SALON_CID)
        print(f"Found {len(reviews)} reviews.")

        for review in reviews:
            # DataForSEO review structure varies, mapping fields safely
            # Assuming 'id', 'reviewer_name', 'rating', 'text', 'time'
            # Adjust keys based on actual DataForSEO 'live' output structure
            # Commonly: 'review_id', 'review_text', 'rating_value', 'reviewer_name', 'review_datetime_utc'
            
            # Use a fallback key mapping strategy if needed, or assume standard keys
            review_id = review.get('id_review') or review.get('review_id')
            if not review_id:
                continue

            if db.review_exists(review_id):
                continue
            
            print(f"Processing new review: {review_id}")
            
            author = review.get('reviewer_name', 'Anonymous')
            rating = review.get('rating_value', 0)
            text = review.get('review_text', '')
            
            # Analyze with Intelligence Router (Gemini + Claude + DeepSeek)
            # Capture FULL raw data for analytics
            analysis = self.router.process_review(text, author, rating, context_image_path=CONTEXT_IMAGE_PATH)
            
            # Prepare DB Payload
            review_record = {
                "review_id": review_id,
                "author_name": author,
                "rating": rating,
                "original_text": text,
                "translated_summary": analysis.get('vietnamese_summary', ''),
                "draft_reply": analysis.get('english_reply', ''),
                "sentiment": analysis.get('sentiment', 'Neutral'),
                "tags": analysis.get('tags', []),
                "raw_data": review, # Save full JSON
                "status": "PENDING_APPROVAL",
                "created_at": "now()"
            }
            
            # Insert to DB
            db.insert_review(review_record)
            
            # Send SMS Alert
            self.gatekeeper.send_review_alert(
                author=author,
                original_text=text,
                vietnamese_summary=review_record['translated_summary'],
                english_draft=review_record['draft_reply'],
                vietnamese_draft=analysis.get('vietnamese_reply', '')
            )

    def process_approvals(self):
        # Check if owner said YES
        approval_status = self.gatekeeper.check_approval()
        
        if approval_status == "APPROVED":
            print("Owner approved via SMS!")
            
            # Find Pending Reviews
            # Supabase filter. 
            # Strategy: Get the LATEST pending review. 
            # In a real app we might store 'last_sent_sms_review_id' in a state file or DB
            try:
                response = db.get_client().table("reviews")\
                    .select("*")\
                    .eq("status", "PENDING_APPROVAL")\
                    .order("created_at", desc=True)\
                    .limit(1)\
                    .execute()
                
                pending_reviews = response.data
                
                if pending_reviews:
                    review_to_post = pending_reviews[0]
                    print(f"posting reply for {review_to_post['review_id']}")
                    
                    # Post to Google
                    success = self.poster.post_reply(
                        review_to_post['review_id'],
                        review_to_post['draft_reply']
                    )
                    
                    if success:
                        # Update DB
                        print("Successfully posted.")
                        db.update_status(
                            review_to_post['review_id'], 
                            "POSTED",
                            {"posted_at": "now()"}
                        )
                        # Optional: Send "Posted!" SMS
                else:
                    print("Owner said YES but no pending reviews found.")
                    
            except Exception as e:
                print(f"Error processing approval: {e}")

if __name__ == "__main__":
    agent = SalonAgent()
    agent.run()
