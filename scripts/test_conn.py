
import os
import sys
# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from google import genai
from config import settings


def test_gemini():
    print(f"Testing Gemini with key: {settings.GEMINI_API_KEY[:5]}...")
    
    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        print("0. Listing Models...")
        for m in client.models.list(config={'page_size': 50}):
            print(f" - {m.name}")

        print("\n1. Testing Simple Generation (gemini-flash-latest)...")
        # Trying alias
        response = client.models.generate_content(
            model='gemini-flash-latest',
            contents='Hello, are you working?'
        )
        print(f"Success! Response: {response.text}")
        
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        # import traceback
        # traceback.print_exc()

if __name__ == "__main__":
    test_gemini()

