import requests
import json
import time
from base64 import b64encode
from config import settings

class DataForSEOClient:
    BASE_URL = "https://api.dataforseo.com/v3/business_data/google/reviews/live"

    def __init__(self):
        self.login = settings.DATAFORSEO_LOGIN
        self.password = settings.DATAFORSEO_PASSWORD
        if not self.login or not self.password:
            print("Warning: DataForSEO credentials missing.")
        
    def _get_headers(self):
        return {
            'Authorization': 'Basic ' + b64encode(f"{self.login}:{self.password}".encode('utf-8')).decode('utf-8'),
            'Content-Type': 'application/json'
        }

    def fetch_reviews(self, cid: str, depth: int = 10):
        """
        Fetches the latest reviews for a given Google Maps CID.
        Uses the 'live' endpoint for immediate results.
        """
        payload = [{
            "language_code": "en",
            "location_code": 2840, # Example: USA, but CID usually overrides or requires specific match. 
            # Actually for CID based search, we might not need location_code if generic, but usually safer to pass none or broad.
            # Let's rely on 'cid' parameter filter.
            "cid": cid,
            "depth": depth,
            "sort_by": "date",
            "order": "desc"
        }]

        try:
            response = requests.post(
                self.BASE_URL,
                headers=self._get_headers(),
                data=json.dumps(payload)
            )
            response.raise_for_status()
            result = response.json()
            
            # Basic validation
            if result.get('status_code') == 20000:
                tasks = result.get('tasks', [])
                if tasks:
                    # Extracts reviews list from the first task result
                    for task in tasks:
                        if task.get('result'):
                            return task['result'][0].get('items', [])
            else:
                print(f"DataForSEO Error: {result.get('status_message')}")
                return []
                
        except Exception as e:
            print(f"Error fetching reviews: {e}")
            return []
        
        return []
