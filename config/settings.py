import os
from dotenv import load_dotenv

load_dotenv()

# DataForSEO
DATAFORSEO_LOGIN = os.getenv("DATAFORSEO_LOGIN")
DATAFORSEO_PASSWORD = os.getenv("DATAFORSEO_PASSWORD")
DATAFORSEO_USE_SANDBOX = os.getenv("DATAFORSEO_USE_SANDBOX", "False").lower() == "true"

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Project Settings
SALON_CID = os.getenv("SALON_CID")
SALON_NAME = os.getenv("SALON_NAME", "N/A")
SEARCH_QUERY = os.getenv("SEARCH_QUERY")
DRY_RUN = os.getenv("DRY_RUN", "False").lower() == "true"
DRY_RUN_REVIEWS_FILE = os.getenv("DRY_RUN_REVIEWS_FILE", "scripts/data/test_reviews.json")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Gemini (used for image/vision analysis)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
VISION_MODEL = os.getenv("VISION_MODEL", "gemini-2.0-flash")
