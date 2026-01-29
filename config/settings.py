import os
from dotenv import load_dotenv

load_dotenv()

# DataForSEO
DATAFORSEO_LOGIN = os.getenv("DATAFORSEO_LOGIN")
DATAFORSEO_PASSWORD = os.getenv("DATAFORSEO_PASSWORD")

# Google Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
OWNER_PHONE_NUMBER = os.getenv("OWNER_PHONE_NUMBER")

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Google Business Profile
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")

# Project Settings
GEMINI_MODEL_NAME = "gemini-1.5-flash"
CLAUDE_MODEL_NAME = "claude-3-5-sonnet-20241022"
DEEPSEEK_MODEL_NAME = "deepseek-chat" # or specific V3 endpoint
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
SALON_CID = os.getenv("SALON_CID") # Google Maps CID for the salon
