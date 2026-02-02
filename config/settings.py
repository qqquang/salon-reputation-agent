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
SEARCH_QUERY = os.getenv("SEARCH_QUERY")
