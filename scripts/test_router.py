
import sys
import os
import json

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.processing.router import IntelligenceRouter

def test_router():
    router = IntelligenceRouter()
    
    print("--- Gemini Router CLI Tester ---")
    print("Loading 'scripts/test_reviews.json'...")
    
    results = []
    
    try:
        base_dir = os.path.dirname(__file__)
        data_dir = os.path.join(base_dir, 'data')
        json_path = os.path.join(data_dir, 'test_reviews.json')
        output_path = os.path.join(data_dir, 'test_results.json')
        
        with open(json_path, 'r') as f:
            test_cases = json.load(f)
        
        print(f"Loaded {len(test_cases)} reviews.")
        print("-" * 30)

        for i, case in enumerate(test_cases):
            # Support both wrapped format (with 'data' or 'input' key) and raw format
            data = case.get('data') or case.get('input') or case 
            
            # Normalize data
            # Support multiple key variations
            text = (data.get('review_text') or 
                   data.get('original_review_text') or 
                   data.get('original_text') or 
                   "")
                   
            author = (data.get('profile_name') or 
                     data.get('author_name') or 
                     'Test User')
            
            review_id = data.get('review_id') or data.get('id') or f"test_{i}"
            
            # Handle rating
            rating = 5
            if 'rating' in data:
                r_val = data['rating']
                if isinstance(r_val, dict):
                    rating = r_val.get('value', 5)
                else:
                    rating = r_val
            
            print(f"[{i+1}] Processing review from {author}...")
            
            review_data = {
                "review_id": review_id,
                "original_text": text,
                "rating": int(rating) if rating else 5,
                "author_name": author,
                "salon_name": "LuxeNails"
            }
            
            # Synthetic History for testing context
            mock_history = [
                "Thanks for visiting! We love your style. @LuxeNails",
                "So glad you enjoyed the pedicure! Hope to see you soon.",
                "We are sorry to hear about the wait time. Please DM us."
            ]
            
            try:
                result = router.process_review(review_data, history=mock_history)
                
                # Structure output for the results file
                output_record = {
                    "input": review_data,
                    "analysis": result
                }
                results.append(output_record)
                
                print(json.dumps(result, indent=2, ensure_ascii=False))
            except Exception as e:
                print(f"Failed to process review: {e}")
                
            print("-" * 30)
            
        # Save results to file
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
            
        print(f"\n✅ Results (including Draft Responses) saved to:\n{output_path}")

    except FileNotFoundError:
        print("Error: 'scripts/test_reviews.json' not found.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_router()
