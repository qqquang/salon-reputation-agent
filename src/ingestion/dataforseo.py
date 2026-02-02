import requests
import json
import time
from base64 import b64encode
from config import settings

class DataForSEOClient:
    def __init__(self):
        self.login = settings.DATAFORSEO_LOGIN
        self.password = settings.DATAFORSEO_PASSWORD
        
        # Determine Base Domain (Root v3)
        if settings.DATAFORSEO_USE_SANDBOX:
            print("Using DataForSEO Sandbox Environment")
            self.base_domain = "https://sandbox.dataforseo.com/v3"
        else:
            self.base_domain = "https://api.dataforseo.com/v3"

        if not self.login or not self.password:
            print("Warning: DataForSEO credentials missing.")
        
    def _get_headers(self):
        return {
            'Authorization': 'Basic ' + b64encode(f"{self.login}:{self.password}".encode('utf-8')).decode('utf-8'),
            'Content-Type': 'application/json'
        }

    def fetch_reviews(self, cid: str, depth: int = 700):
        """
        Fetches reviews using the Task Post/Get (Async) method.
        This handles cases where data is not in 'Live' cache.
        """
        # 1. Post Task
        post_endpoint = f"{self.base_domain}/business_data/google/reviews/task_post"
        payload = [{
            "language_name": "English",
            "language_code": "en",
            "location_name": "United States",
            "location_code": 2840,
            "cid": cid, # Use the ID from search
            "depth": depth
        }]
        
        print(f"DEBUG: Posting review task for {cid}...")
        post_response = self._make_request(post_endpoint, payload, is_task_post=True)
        if not post_response:
             # Fallback: Try sending it as 'data_id' if 'cid' failed logic? 
             # But let's assume cid works or we rely on the error.
             print("DEBUG: Task Post failed.")
             return []

        task_id = post_response
        print(f"DEBUG: Task {task_id} started. Waiting for results...")
        
        # 2. Poll for Results
        get_endpoint = f"{self.base_domain}/business_data/google/reviews/task_get/{task_id}"
        
        for i in range(30): # Try for 60 seconds (30 * 2s)
            time.sleep(2)
            try:
                response = requests.get(get_endpoint, headers=self._get_headers())
                result = response.json()
                
                if result.get('status_code') == 20000:
                    tasks = result.get('tasks', [])
                    if tasks:
                        task_status = tasks[0].get('status_code')
                        
                        if task_status == 20000:
                            # Task Complete!
                            items = tasks[0].get('result', [])
                            if items:
                                return items[0].get('items', [])
                            return []
                        elif task_status == 40400:
                            print(f"DEBUG: Task {task_id} returned Not Found.")
                            return []
                        else:
                            # Still running (10100 is queue, 10200 is running)
                            if i % 5 == 0:
                                print(f"DEBUG: Task {task_id} is running (Status: {task_status})...")
            except Exception as e:
                print(f"Error polling task {task_id}: {e}")
                
        print(f"DEBUG: Task {task_id} timed out.")
        return []

    def search_businesses(self, keyword: str):
        """
        Searches for businesses on Google Maps.
        Endpoint: serp/google/maps/live/advanced
        """
        endpoint = f"{self.base_domain}/serp/google/maps/live/advanced"
        
        payload = [{
            "keyword": keyword,
            "language_code": "en",
            "location_code": 2840 # USA
        }]
        
        return self._make_request(endpoint, payload)

    def _make_request(self, url: str, payload: list, is_task_post: bool = False):
        try:
            print(f"DEBUG: Requesting {url}") # Make this visible
            response = requests.post(
                url,
                headers=self._get_headers(),
                data=json.dumps(payload)
            )
            # print(f"DEBUG: Request to {url} status: {response.status_code}") 
            response.raise_for_status()
            result = response.json()
            
            # Basic validation
            if result.get('status_code') == 20000:
                tasks = result.get('tasks', [])
                if tasks:
                    for task in tasks:
                        # Check individual task status!
                        # 20000 = Ok, 20100 = Task Created
                        status = task.get('status_code')
                        if status != 20000 and status != 20100:
                            print(f"DataForSEO Task Error: {task.get('status_message')} (Code: {status})")
                            if is_task_post:
                                return None

                        # If posting a task, we just want the ID
                        if is_task_post:
                            return task.get('id')
                            
                        # If getting results
                        if task.get('result'):
                             # Debug: Print structure if fetching reviews
                            if "reviews" in url:
                                # print(f"DEBUG: Review Response Structure: {task['result'][0].keys()}")
                                pass
                            
                            return task['result'][0].get('items', [])
            else:
                print(f"DataForSEO Error: {result.get('status_message')}")
                if "reviews" in url:
                     print("Full Response:", json.dumps(result, indent=2))
                return []
                
        except Exception as e:
            print(f"Error making request to {url}: {e}")
            if 'response' in locals():
                print(response.text)
            return []
        
        return []
