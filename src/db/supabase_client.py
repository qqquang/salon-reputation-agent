from supabase import create_client, Client
from datetime import datetime, timezone
from config import settings

class SupabaseClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SupabaseClient, cls).__new__(cls)
            if settings.DRY_RUN:
                cls._instance.client = None
            elif not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
                raise ValueError("Supabase URL and Key must be set in .env")
            else:
                cls._instance.client: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        return cls._instance

    def get_client(self) -> Client:
        return self.client

    def review_exists(self, review_id: str) -> bool:
        """Checks if a review ID already exists in the database."""
        if settings.DRY_RUN or self.client is None:
            return False
        try:
            response = self.client.table("reviews").select("review_id", count="exact").eq("review_id", review_id).execute()
            # If count is not None and > 0, it exists. 
            # Note: exact count might require head=true or similar depending on implementation, 
            # but select with filter usually returns data.
            return len(response.data or []) > 0
        except Exception as e:
            print(f"Error checking review existence: {e}")
            return False

    def insert_review(self, review_data: dict):
        """Inserts a new review into the database."""
        if settings.DRY_RUN or self.client is None:
            print(f"[DRY_RUN] Would insert review {review_data.get('review_id')} with status={review_data.get('status')}")
            return
        try:
            self.client.table("reviews").upsert(review_data, on_conflict="review_id").execute()
            print(f"Inserted review {review_data.get('review_id')}")
        except Exception as e:
            print(f"Error inserting review: {e}")
            raise

    def update_status(self, review_id: str, status: str, extra_data: dict = None):
        """Updates the status of a review."""
        update_payload = {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}
        if extra_data:
            update_payload.update(extra_data)
        if settings.DRY_RUN or self.client is None:
            print(f"[DRY_RUN] Would update review {review_id} to status={status}")
            return
        
        try:
            self.client.table("reviews").update(update_payload).eq("review_id", review_id).execute()
            print(f"Updated review {review_id} status to {status}")
        except Exception as e:
            print(f"Error updating review status: {e}")
            raise

    def get_recent_responses(self, limit: int = 20) -> list[str]:
        """Fetches the last 'limit' draft responses to provide context."""
        if settings.DRY_RUN or self.client is None:
            return []
        try:
            response = self.client.table("reviews") \
                .select("draft_response") \
                .not_.is_("draft_response", "null") \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            
            return [r['draft_response'] for r in response.data if r.get('draft_response')]
        except Exception as e:
            print(f"Error fetching recent responses: {e}")
            return []

    def get_recent_review_context(self, limit: int = 20) -> list[dict]:
        """Fetches recent review/response pairs for drafting context."""
        if settings.DRY_RUN or self.client is None:
            return []
        try:
            response = self.client.table("reviews") \
                .select("review_id,author_name,rating,original_text,draft_response,created_at") \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()

            return response.data or []
        except Exception as e:
            print(f"Error fetching recent review context: {e}")
            return []

    def update_salon_name_by_cid(self, cid: str, new_name: str) -> int:
        """
        Updates salon_name for all reviews with the given CID.
        Called automatically when Google renames a business.
        Returns the number of rows updated.
        """
        if settings.DRY_RUN or self.client is None:
            print(f"[DRY_RUN] Would rename all reviews for CID {cid} to '{new_name}'")
            return 0
        try:
            from datetime import datetime, timezone
            response = self.client.table("reviews") \
                .update({"salon_name": new_name, "updated_at": datetime.now(timezone.utc).isoformat()}) \
                .eq("cid", cid) \
                .neq("salon_name", new_name) \
                .execute()
            count = len(response.data) if response.data else 0
            if count > 0:
                print(f"  ✅ Auto-renamed {count} reviews for CID {cid} → '{new_name}'")
            return count
        except Exception as e:
            print(f"Error updating salon name for CID {cid}: {e}")
            return 0

    def get_salon_name(self, cid: str) -> str:
        """
        Attempts to find a valid salon name for the given CID from existing records.
        Returns None if not found or if only placeholders exist.
        """
        if settings.DRY_RUN or self.client is None:
            return None
        try:
            response = self.client.table("reviews") \
                .select("salon_name") \
                .eq("cid", cid) \
                .neq("salon_name", "Unknown Salon") \
                .neq("salon_name", "N/A") \
                .limit(1) \
                .execute()
            
            if response.data:
                return response.data[0].get('salon_name')
        except Exception as e:
            print(f"Error fetching salon name for CID {cid}: {e}")
        return None

# Global instance for easy access
db = SupabaseClient()

def append_history_context(history_context, review_id, review_data, draft_response, limit=20):
    """Shared helper: maintains a rolling, de-duplicated in-memory review/response context."""
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
