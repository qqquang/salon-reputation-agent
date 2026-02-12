import os
import json
import hashlib
import re
from datetime import datetime, timezone
from openai import OpenAI
from config import settings

class IntelligenceRouter:
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set in environment variables.")
        
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=60.0,
            max_retries=2
        )
        self.model = settings.OPENAI_MODEL
        
        # Load prompts configuration
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            prompts_path = os.path.join(base_dir, 'config', 'prompts.json')
            with open(prompts_path, 'r') as f:
                self.prompts = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load prompts.json: {e}")
            self.prompts = {}

        # Load optional brand context configuration.
        try:
            brand_context_path = os.path.join(base_dir, 'config', 'brand_context.json')
            with open(brand_context_path, 'r') as f:
                self.brand_context = json.load(f)
        except Exception:
            self.brand_context = {}

    def _build_brand_context(self) -> str:
        if not isinstance(self.brand_context, dict) or not self.brand_context:
            return "No additional brand context provided."

        lines = []
        identity = self.brand_context.get("identity")
        if identity:
            lines.append(f"Identity: {identity}")

        tone = self.brand_context.get("tone")
        if isinstance(tone, list) and tone:
            lines.append(f"Tone keywords: {', '.join(tone)}")

        differentiators = self.brand_context.get("differentiators")
        if isinstance(differentiators, list) and differentiators:
            lines.append(f"Differentiators: {', '.join(differentiators)}")

        services = self.brand_context.get("services")
        if isinstance(services, list) and services:
            lines.append(f"Core services: {', '.join(services)}")

        avoid_phrases = self.brand_context.get("avoid_phrases")
        if isinstance(avoid_phrases, list) and avoid_phrases:
            lines.append(f"Avoid phrases: {', '.join(avoid_phrases)}")

        return "\n".join(lines) if lines else "No additional brand context provided."

    def _build_style_hint(self, review_data: dict, sentiment_score: int, category: str) -> str:
        review_id = review_data.get("review_id", "default")
        seed = int(hashlib.sha256(str(review_id).encode("utf-8")).hexdigest(), 16)

        opening_styles = [
            "Start with gratitude for their time and feedback.",
            "Start by reflecting one positive detail from their experience.",
            "Start with an upbeat appreciation line."
        ]
        closing_styles = [
            "Close with a warm invitation to return soon.",
            "Close with a community-forward line that feels personal.",
            "Close with a short, polished appreciation sentence."
        ]

        if sentiment_score <= 4:
            opening_styles = [
                "Start with empathy and acknowledgment of their concern.",
                "Start by validating their experience in plain language.",
                "Start with calm ownership and intent to improve."
            ]
            closing_styles = [
                "Close by inviting direct private follow-up and resolution.",
                "Close with a respectful next-step invitation for support.",
                "Close with accountability and a clear private contact cue."
            ]

        opening = opening_styles[seed % len(opening_styles)]
        closing = closing_styles[(seed // 7) % len(closing_styles)]
        closing_options = [
            "We are excited to pamper you again soon.",
            "Thanks for trusting us with your nails.",
            "We look forward to your next set at Mi Nail Belleville.",
            "See you soon for your next nail refresh.",
            "We can't wait to welcome you in again.",
            "We appreciate you choosing Mi Nail Belleville."
        ]

        option_a = closing_options[seed % len(closing_options)]
        option_b = closing_options[(seed // 3) % len(closing_options)]
        option_c = closing_options[(seed // 5) % len(closing_options)]

        return (
            f"Category={category}; Sentiment={sentiment_score}. "
            f"Opening style: {opening} "
            f"Closing style: {closing} "
            f"Preferred closing options (pick one not repeated in Recent Responses): "
            f"{option_a} | {option_b} | {option_c}"
        )

    def _normalize_text(self, text: str) -> str:
        text = (text or "").lower().strip()
        text = re.sub(r"[^a-z0-9\s]", "", text)
        return re.sub(r"\s+", " ", text).strip()

    def _extract_last_sentence(self, text: str) -> str:
        if not text:
            return ""
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        return parts[-1] if parts else text.strip()

    def _build_recent_closings(self, history: list[str]) -> list[str]:
        closings = []
        for h in history or []:
            closing = self._extract_last_sentence(h)
            normalized = self._normalize_text(closing)
            if normalized:
                closings.append(normalized)
        return closings

    def _generate_text(self, prompt: str) -> str:
        response = self.client.responses.create(
            model=self.model,
            input=prompt
        )

        text = getattr(response, "output_text", None)
        if text:
            return text.strip()

        # Fallback extraction for SDK/version differences.
        output = getattr(response, "output", []) or []
        parts = []
        for item in output:
            for content in getattr(item, "content", []) or []:
                part_text = getattr(content, "text", None)
                if part_text is None and isinstance(content, dict):
                    part_text = content.get("text")
                if part_text:
                    parts.append(part_text)
        return "\n".join(parts).strip()

    def process_review(self, review_data: dict, history: list[str] = None) -> dict:
        """
        Main entry point for processing a review.
        Orchestrates the analysis pipeline using OpenAI.
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
            draft_response = self._draft(review_data, scout_result, history)

            return {
                "scout": scout_result,
                "vietnamese_summary": vietnamese_summary,
                "consult": consult_result,
                "draft_response": draft_response,
                "processed_at": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            print(f"Error processing review {review_data.get('review_id')}: {e}")
            return {
                "error": str(e),
                "processed_at": datetime.now(timezone.utc).isoformat()
            }

    def _scout(self, review_data: dict) -> dict:
        """
        Step 1: Quick analysis of sentiment, risk, and category.
        """
        text = review_data.get('original_text', '')
        rating = review_data.get('rating', 0)
        rating_to_sentiment = {
            5: 9,
            4: 8,
            3: 6,
            2: 4,
            1: 2,
        }
        
        # Load prompt from config or fallback
        prompt_template = self.prompts.get('scout', "Analyze this review: {text}")
        prompt = prompt_template.format(text=text, rating=rating)
        
        try:
            text = self._generate_text(prompt)
            scout = json.loads(text)
            if not (review_data.get('original_text') or '').strip():
                try:
                    rating_int = int(float(rating))
                except Exception:
                    rating_int = 3
                scout['sentiment_score'] = rating_to_sentiment.get(rating_int, 6)
                scout['risk_flag'] = False
                scout['category'] = 'Other'
            return scout
        except Exception as e:
            print(f"Scout Error: {e}")
            if not (review_data.get('original_text') or '').strip():
                try:
                    rating_int = int(float(rating))
                except Exception:
                    rating_int = 3
                return {
                    "sentiment_score": rating_to_sentiment.get(rating_int, 6),
                    "risk_flag": False,
                    "category": "Other"
                }
            return {"sentiment_score": 0, "risk_flag": False, "category": "Other"}

    def _translate(self, review_data: dict, scout_result: dict) -> str:
        """
        Step 2: Summarize the review in Vietnamese for the owner.
        """
        text = review_data.get('original_text', '')
        category = scout_result.get('category')
        
        prompt_template = self.prompts.get('translate', "Summarize in Vietnamese: {text}")
        prompt = prompt_template.format(text=text, category=category)
        
        try:
            return self._generate_text(prompt)
        except Exception as e:
             print(f"Translate Error: {e}")
             return "Lỗi dịch thuật."

    def _consult(self, review_data: dict) -> dict:
        """
        Step 3: Deep dive analysis for identifying root cause and strategy.
        """
        text = review_data.get('original_text', '')
        
        prompt_template = self.prompts.get('consult', "Analyze this review: {text}")
        prompt = prompt_template.format(text=text)
        
        try:
            text = self._generate_text(prompt)
            return json.loads(text)
        except Exception:
            return {}

    def _draft(self, review_data: dict, scout_result: dict, history: list[str] = None) -> str:
        """
        Step 4: Draft a polite, professional response.
        """
        text = review_data.get('original_text', '')
        author = review_data.get('author_name', 'client')
        category = scout_result.get('category')
        salon_name = review_data.get('salon_name', 'our salon')

        # Conditional Emoji Logic
        sentiment_score = scout_result.get('sentiment_score', 5)
        if sentiment_score < 7:
            emoji_instruction = "DO NOT use any emojis."
        else:
            emoji_instruction = "Use 1-2 appropriate emojis."

        # Format history for prompt
        history_str = "\n".join([f"- {h}" for h in (history or [])]) if history else "None."
        brand_context = self._build_brand_context()
        style_hint = self._build_style_hint(review_data, sentiment_score, category)

        prompt_template = self.prompts.get('draft', "Write a response to: {text}")
        prompt = prompt_template.format(
            text=text, 
            author=author, 
            category=category, 
            salon_name=salon_name,
            emoji_instruction=emoji_instruction,
            context_history=history_str,
            brand_context=brand_context,
            style_hint=style_hint
        )
        
        try:
            draft = self._generate_text(prompt)
            recent_closings = self._build_recent_closings(history)
            new_closing = self._normalize_text(self._extract_last_sentence(draft))

            if new_closing and new_closing in recent_closings:
                retry_prompt = (
                    f"{prompt}\n\nRegenerate once with a different final sentence than these recent closings:\n"
                    + "\n".join([f"- {c}" for c in recent_closings])
                )
                draft_retry = self._generate_text(retry_prompt)
                retry_closing = self._normalize_text(self._extract_last_sentence(draft_retry))
                if retry_closing and retry_closing not in recent_closings:
                    return draft_retry

            return draft
        except Exception:
            return "Thank you for your feedback."
