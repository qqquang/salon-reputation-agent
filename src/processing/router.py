import os
import json
import google.generativeai as genai
from anthropic import Anthropic
from openai import OpenAI
from config import settings
from google.ai.generativelanguage_v1beta.types import content

class IntelligenceRouter:
    def __init__(self):
        # 1. Setup Gemini (Scout & Drafter)
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not set.")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.gemini_model = genai.GenerativeModel(settings.GEMINI_MODEL_NAME)

        # 2. Setup Claude (Consultant)
        if settings.CLAUDE_API_KEY:
            self.claude_client = Anthropic(api_key=settings.CLAUDE_API_KEY)
        else:
            print("Warning: CLAUDE_API_KEY not set. 'Consultant' mode will be disabled.")
            self.claude_client = None

        # 3. Setup DeepSeek (Translator)
        if settings.DEEPSEEK_API_KEY:
            # DeepSeek uses OpenAI-compatible API
            self.deepseek_client = OpenAI(
                api_key=settings.DEEPSEEK_API_KEY,
                base_url="https://api.deepseek.com"
            )
        else:
            print("Warning: DEEPSEEK_API_KEY not set. 'Translator' mode will fallback to Gemini.")
            self.deepseek_client = None

    def process_review(self, text: str, author: str, rating: int, context_image_path: str = None) -> dict:
        """
        Orchestrates the multi-model analysis.
        """
        print(f"--- Routing Review from {author} ({rating} stars) ---")
        
        # Step 1: The Scout (Gemini) - Cheap & Fast
        scout_report = self._scout(text, rating)
        sentiment = scout_report.get('sentiment', 'Neutral')
        is_complex = scout_report.get('is_complex', False)
        print(f"Scout Report: Sentiment={sentiment}, Complex={is_complex}")

        # Step 2: The Consultant (Claude) - Only if needed
        consulting_notes = ""
        if (sentiment == "Negative" or is_complex) and self.claude_client:
            print("Triggering Consultant (Claude)...")
            consulting_notes = self._consult(text, rating)
        
        # Step 3: The Drafter (Gemini + Vision)
        # drafts English reply based on policy/context
        print("Triggering Drafter (Gemini)...")
        english_draft = self._draft(text, author, sentiment, consulting_notes, context_image_path)

        # Step 4: The Translator (DeepSeek)
        # Summarizes for owner and translates the draft
        print("Triggering Translator (DeepSeek)...")
        translation_report = self._translate(text, english_draft, consulting_notes)

        # Compile Result
        return {
            "sentiment": sentiment,
            "tags": scout_report.get('tags', []),
            "vietnamese_summary": translation_report.get('vietnamese_summary', ''),
            "english_reply": english_draft,
            "vietnamese_reply": translation_report.get('vietnamese_reply', ''), # Translation of the draft
            "consulting_notes": consulting_notes
        }

    def _scout(self, text: str, rating: int) -> dict:
        """
        Gemini 1.5 Flash: Determines sentiment and complexity.
        """
        prompt = f"""
        Analyze this Google Review for a Nail Salon.
        Review: "{text}"
        Rating: {rating}/5
        
        Return JSON with:
        - sentiment: "Positive", "Negative", "Neutral"
        - tags: list of keywords (e.g. "Price", "Service", "Cleanliness")
        - is_complex: Boolean. True if the review is sarcastic, passive-aggressive, or detailed/long. False if simple.
        """
        try:
            response = self.gemini_model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    response_schema={
                        "type": "OBJECT",
                        "properties": {
                            "sentiment": {"type": "STRING", "enum": ["Positive", "Negative", "Neutral"]},
                            "tags": {"type": "ARRAY", "items": {"type": "STRING"}},
                            "is_complex": {"type": "BOOLEAN"}
                        }
                    }
                )
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"Scout Error: {e}")
            return {"sentiment": "Neutral", "tags": [], "is_complex": False}

    def _consult(self, text: str, rating: int) -> str:
        """
        Claude 3.5 Sonnet: Deep cultural/emotional analysis.
        """
        if not self.claude_client:
            return ""

        system_msg = """
        You are a consultant for a Vietnamese-American salon owner. 
        Your job is to explain the "hidden meaning" of this American customer's review.
        Explain WHY they are upset, focusing on cultural nuances (e.g. "They aren't just mad about the price, they feel disrespected because...").
        Keep it brief but insightful.
        """
        
        try:
            message = self.claude_client.messages.create(
                model=settings.CLAUDE_MODEL_NAME,
                max_tokens=300,
                system=system_msg,
                messages=[
                    {"role": "user", "content": f"Review ({rating} stars): {text}"}
                ]
            )
            return message.content[0].text
        except Exception as e:
            print(f"Consultant Error: {e}")
            return f"Could not consult: {e}"

    def _draft(self, text: str, author: str, sentiment: str, consulting_notes: str, context_image_path: str) -> str:
        """
        Gemini 1.5 Flash (Multimodal): Writes the English response.
        """
        parts = []
        
        prompt = f"""
        You are the professional manager of this salon. Draft a reply to this review.
        
        Review: "{text}"
        Author: {author}
        Sentiment: {sentiment}
        Consultant's Insight (Internal): {consulting_notes}
        
        Goal:
        - If Positive: Warm thank you.
        - If Negative: Professional, polite, but FIRM on policy if needed. Use the Consultant's notes to address the REAL issue.
        - If the Context Image (Price List/Policy) is provided, USE IT. If they claim a price is wrong, politely correct them based on the image.
        
        Return ONLY the raw text of the reply. No JSON.
        """
        parts.append(prompt)

        if context_image_path and os.path.exists(context_image_path):
            try:
                # Gemini Helper for local file
                # Ideally we upload via File API for caching, but for specific one-off:
                img_file = genai.upload_file(context_image_path)
                parts.append(img_file)
            except Exception as e:
                print(f"Vision Error: {e}")

        try:
            response = self.gemini_model.generate_content(parts)
            return response.text.strip()
        except Exception as e:
            print(f"Draft Error: {e}")
            return "Thank you for your feedback."

    def _translate(self, review_text: str, english_reply: str, consulting_notes: str) -> dict:
        """
        DeepSeek-V3: Translates Summary and Reply into Vietnamese.
        """
        # Fallback to Gemini if DeepSeek not set
        if not self.deepseek_client:
            # Simple fallback implementation using Gemini if needed, 
            # but for now let's just return empty or error to prompt user to set key.
            # actually, let's implement a quick fallback to Gemini since we have it.
            return self._scout_translate_fallback(review_text, english_reply, consulting_notes)

        prompt = f"""
        You are a translator for a Vietnamese salon owner.
        
        1. Context:
        Customer Review: "{review_text}"
        Consultant Notes: "{consulting_notes}"
        Proposed English Reply: "{english_reply}"
        
        2. Tasks:
        A. "vietnamese_summary": Summarize the review in Vietnamese. 
           - Explain what the customer wants.
           - Include the "Consultant Notes" if they exist (translated).
           - Style: Respectful but clear ("Cô ơi, khách này nói...").
           
        B. "vietnamese_reply": Translate the "Proposed English Reply" into Vietnamese so the owner understands exactly what will be posted.
        
        Return JSON:
        {{
            "vietnamese_summary": "...",
            "vietnamese_reply": "..."
        }}
        """
        
        try:
            response = self.deepseek_client.chat.completions.create(
                model=settings.DEEPSEEK_MODEL_NAME,
                messages=[
                    {"role": "system", "content": "You are a helpful translator JSON bot."},
                    {"role": "user", "content": prompt}
                ],
                response_format={
                    'type': 'json_object'
                }
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"DeepSeek Error: {e}")
            return {"vietnamese_summary": "Lỗi dịch thuật (Translation Error)", "vietnamese_reply": "Error"}

    def _scout_translate_fallback(self, review_text, english_reply, consulting_notes):
        # Fallback using Gemini if DeepSeek is missing (to prevent crash)
        prompt = f"""
        Translate to Vietnamese (JSON):
        Review: {review_text}
        Reply: {english_reply}
        
        Format: {{ "vietnamese_summary": "...", "vietnamese_reply": "..." }}
        """
        try:
            res = self.gemini_model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
            return json.loads(res.text)
        except:
            return {"vietnamese_summary": "Error", "vietnamese_reply": "Error"}
