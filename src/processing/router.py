import os
import json
from google import genai
from config import settings

class IntelligenceRouter:
    def __init__(self):
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set in environment variables.")
        
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)

    def process_review(self, review_data: dict) -> dict:
        """
        Main entry point for processing a review.
        Orchestrates the analysis pipeline using Gemini.
        """
        try:
            # 1. Scout: Analyze sentiment and risk
            scout_result = self._scout(review_data)
            
            # 2. Translate: Summarize in Vietnamese
            vietnamese_summary = self._translate(review_data, scout_result)
            
            # 3. Consult: Deep dive if risky (Optional optimization: only run if risk=True)
            consult_result = {}
            if scout_result.get('risk_flag'):
                consult_result = self._consult(review_data)

            # 4. Draft: Create a response
            draft_response = self._draft(review_data, scout_result)

            return {
                "scout": scout_result,
                "vietnamese_summary": vietnamese_summary,
                "consult": consult_result,
                "draft_response": draft_response,
                "processed_at": "now()" # Placeholder for timestamp
            }
        except Exception as e:
            print(f"Error processing review {review_data.get('review_id')}: {e}")
            return {}

    def _scout(self, review_data: dict) -> dict:
        """
        Step 1: Quick analysis of sentiment, risk, and category.
        """
        text = review_data.get('original_text', '')
        rating = review_data.get('rating', 0)
        
        prompt = f"""
        Analyze this salon review.
        Rating: {rating}/5
        Text: "{text}"

        Return JSON with:
        - sentiment_score (1-10)
        - risk_flag (boolean): true if this review requires urgent attention (e.g. infection, rude staff, refund request).
        - category: One of [Service Quality, Cleanliness, Price, Staff Attitude, Wait Time, Other].
        """
        
        try:
            response = self.client.models.generate_content(
                model='gemini-flash-latest',
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"Scout Error: {e}")
            return {"sentiment_score": 0, "risk_flag": False, "category": "Other"}

    def _translate(self, review_data: dict, scout_result: dict) -> str:
        """
        Step 2: Summarize the review in Vietnamese for the owner.
        """
        text = review_data.get('original_text', '')
        category = scout_result.get('category')
        
        prompt = f"""
        Summarize this review in 1 sentence in Vietnamese for a nail salon owner.
        Focus on the main complaint or compliment.
        Category: {category}
        Review: "{text}"
        """
        
        try:
            response = self.client.models.generate_content(
                model='gemini-flash-latest',
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
             print(f"Translate Error: {e}")
             return "Lỗi dịch thuật."

    def _consult(self, review_data: dict) -> dict:
        """
        Step 3: Deep dive analysis for identifying root cause and strategy.
        """
        text = review_data.get('original_text', '')
        
        prompt = f"""
        You are a crisis management consultant for a salon.
        Analyze this negative review: "{text}"
        
        Return JSON with:
        - root_cause: What exactly went wrong?
        - recommended_action: What should the owner do internally?
        """
        
        try:
            response = self.client.models.generate_content(
                model='gemini-flash-latest',
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )
            return json.loads(response.text)
        except Exception:
            return {}

    def _draft(self, review_data: dict, scout_result: dict) -> str:
        """
        Step 4: Draft a polite, professional response.
        """
        text = review_data.get('original_text', '')
        author = review_data.get('author_name', 'client')
        
        prompt = f"""
        Write a polite, professional response to this salon review.
        Author: {author}
        Review: "{text}"
        Context: The customer is {scout_result.get('category')}.
        
        If positive: Thank them warmly and invite them back.
        If negative: Apologize sincerely, acknowledge the specific issue, and ask them to contact the manager directly to resolve it. Do not be defensive.
        """
        
        try:
            response = self.client.models.generate_content(
                model='gemini-flash-latest',
                contents=prompt
            )
            return response.text.strip()
        except Exception:
            return "Thank you for your feedback."
