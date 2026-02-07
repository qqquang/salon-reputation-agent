from supabase import create_client, Client
from config import settings

class SupabaseClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SupabaseClient, cls).__new__(cls)
            if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
                raise ValueError("Supabase URL and Key must be set in .env")
            cls._instance.client: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        return cls._instance

    def get_client(self) -> Client:
        return self.client

    def review_exists(self, review_id: str) -> bool:
        """Checks if a review ID already exists in the database."""
        try:
            response = self.client.table("reviews").select("review_id", count="exact").eq("review_id", review_id).execute()
            # If count is not None and > 0, it exists. 
            # Note: exact count might require head=true or similar depending on implementation, 
            # but select with filter usually returns data.
            return len(response.data) > 0
        except Exception as e:
            print(f"Error checking review existence: {e}")
            return False

    def insert_review(self, review_data: dict):
        """Inserts a new review into the database."""
        try:
            self.client.table("reviews").insert(review_data).execute()
            print(f"Inserted review {review_data.get('review_id')}")
        except Exception as e:
            print(f"Error inserting review: {e}")
            raise

    def update_status(self, review_id: str, status: str, extra_data: dict = None):
        """Updates the status of a review."""
        update_payload = {"status": status, "updated_at": "now()"}
        if extra_data:
            update_payload.update(extra_data)
        
        try:
            self.client.table("reviews").update(update_payload).eq("review_id", review_id).execute()
            print(f"Updated review {review_id} status to {status}")
        except Exception as e:
            print(f"Error updating review status: {e}")
        except Exception as e:
            print(f"Error updating review status: {e}")
            raise

    def get_recent_responses(self, limit: int = 5) -> list[str]:
        """Fetches the last 'limit' draft responses to provide context."""
        try:
            response = self.client.table("reviews") \
                .select("draft_response") \
                .neq("draft_response", "null") \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            
            return [r['draft_response'] for r in response.data if r.get('draft_response')]
        except Exception as e:
            print(f"Error fetching recent responses: {e}")
            return []

# Global instance for easy access
db = SupabaseClient()
