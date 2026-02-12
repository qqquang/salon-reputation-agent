
import os
import sys
# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from openai import OpenAI
from config import settings


def test_openai():
    if not settings.OPENAI_API_KEY:
        print("OPENAI_API_KEY is missing.")
        return

    print("Testing OpenAI connectivity...")
    
    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)

        print(f"1. Testing simple generation ({settings.OPENAI_MODEL})...")
        response = client.responses.create(
            model=settings.OPENAI_MODEL,
            input="Hello, are you working?"
        )
        print(f"Success! Response: {response.output_text}")
        
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")

if __name__ == "__main__":
    test_openai()
