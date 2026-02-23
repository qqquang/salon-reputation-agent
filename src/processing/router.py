import os
import json
import hashlib
import re
from difflib import SequenceMatcher
from datetime import datetime, timezone
from openai import OpenAI
from google import genai as google_genai
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

        # Gemini client for image analysis (only if key is available)
        self.gemini_client = None
        self.vision_model = settings.VISION_MODEL
        if settings.GEMINI_API_KEY:
            self.gemini_client = google_genai.Client(api_key=settings.GEMINI_API_KEY)
        else:
            print("Warning: GEMINI_API_KEY not set. Image analysis will be skipped.")
        
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
        salon_name = review_data.get("salon_name") or self.brand_context.get("name") or "our salon"
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
            f"We look forward to your next set at {salon_name}.",
            "See you soon for your next nail refresh.",
            "We can't wait to welcome you in again.",
            f"We appreciate you choosing {salon_name}."
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

    def _extract_first_sentence(self, text: str) -> str:
        if not text:
            return ""
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        return parts[0] if parts else text.strip()

    def _extract_last_sentence(self, text: str) -> str:
        if not text:
            return ""
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        return parts[-1] if parts else text.strip()

    def _starts_with_author_name(self, text: str, author: str) -> bool:
        if not text or not author:
            return False
        first_sentence = self._extract_first_sentence(text).strip().lower()
        author_clean = (author or "").strip().lower()
        if not first_sentence or not author_clean:
            return False

        first_token = author_clean.split()[0]
        return first_sentence.startswith(f"{first_token},") or first_sentence.startswith(f"{first_token} ")

    def _build_recent_openings(self, history: list[str]) -> list[str]:
        openings = []
        for h in history or []:
            opening = self._extract_first_sentence(h)
            normalized = self._normalize_text(opening)
            if normalized:
                openings.append(normalized)
        return openings

    def _build_recent_closings(self, history: list[str]) -> list[str]:
        closings = []
        for h in history or []:
            closing = self._extract_last_sentence(h)
            normalized = self._normalize_text(closing)
            if normalized:
                closings.append(normalized)
        return closings

    def _jaccard_similarity(self, a: str, b: str) -> float:
        a_tokens = set((a or "").split())
        b_tokens = set((b or "").split())
        if not a_tokens or not b_tokens:
            return 0.0
        intersection = len(a_tokens.intersection(b_tokens))
        union = len(a_tokens.union(b_tokens))
        return (intersection / union) if union else 0.0

    def _sentence_overlap_ratio(self, a: str, b: str) -> float:
        a_sentences = [
            self._normalize_text(s) for s in re.split(r"(?<=[.!?])\s+", (a or "").strip()) if self._normalize_text(s)
        ]
        b_sentences = [
            self._normalize_text(s) for s in re.split(r"(?<=[.!?])\s+", (b or "").strip()) if self._normalize_text(s)
        ]
        if not a_sentences or not b_sentences:
            return 0.0
        a_set = set(a_sentences)
        b_set = set(b_sentences)
        overlap = len(a_set.intersection(b_set))
        return max(overlap / len(a_set), overlap / len(b_set))

    def _similarity_score(self, a: str, b: str) -> float:
        a_norm = self._normalize_text(a)
        b_norm = self._normalize_text(b)
        if not a_norm or not b_norm:
            return 0.0
        seq_ratio = SequenceMatcher(None, a_norm, b_norm).ratio()
        jaccard = self._jaccard_similarity(a_norm, b_norm)
        sentence_overlap = self._sentence_overlap_ratio(a, b)
        return max(seq_ratio, jaccard, sentence_overlap)

    def _find_most_similar_recent(self, draft: str, recent_responses: list[str]) -> tuple[float, str]:
        best_score = 0.0
        best_match = ""
        for previous in recent_responses[:20]:
            score = self._similarity_score(draft, previous)
            if score > best_score:
                best_score = score
                best_match = previous
        return best_score, best_match

    def _build_recent_review_context_lines(self, history_context: list[dict]) -> str:
        if not history_context:
            return "None."

        lines = []
        for item in history_context:
            rating = item.get("rating")
            rating_label = f"{rating}/5" if rating is not None else "N/A"
            review_text = (item.get("original_text") or "").strip()
            if len(review_text) > 140:
                review_text = review_text[:137].rstrip() + "..."
            if not review_text:
                review_text = "[No review text]"

            draft = (item.get("draft_response") or "").strip()
            if len(draft) > 140:
                draft = draft[:137].rstrip() + "..."
            if not draft:
                draft = "[No draft response]"

            lines.append(f"- Rating {rating_label}; Review: {review_text}; Draft: {draft}")

        return "\n".join(lines)

    def _analyze_images(self, image_urls: list) -> str:
        """
        Uses Gemini Flash to analyze customer-attached review photos.
        Returns a brief description of what's visible: work quality, service type,
        and whether the photos support or contradict the written review.
        Returns empty string if no images or Gemini not configured.
        """
        if not self.gemini_client or not image_urls:
            return ""

        # Limit to first 5 images to keep cost low
        urls = [u for u in image_urls if u][:5]
        if not urls:
            return ""

        try:
            import requests as http_requests
            from google.genai import types as genai_types

            prompt = (
                "You are analyzing nail salon review photos.\n"
                "For each photo, briefly note:\n"
                "1. What service is shown (manicure, pedicure, nail art, etc.)\n"
                "2. Apparent work quality (clean lines, even color, shaping, any visible issues)\n"
                "3. One-line overall impression\n\n"
                "Be factual and concise. Total response max 80 words."
            )

            parts = [genai_types.Part(text=prompt)]
            for url in urls:
                try:
                    resp = http_requests.get(url, timeout=10)
                    resp.raise_for_status()
                    content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
                    parts.append(genai_types.Part(
                        inline_data=genai_types.Blob(
                            mime_type=content_type,
                            data=resp.content
                        )
                    ))
                except Exception as img_err:
                    print(f"   [Vision] Could not fetch image {url[:60]}...: {img_err}")

            if len(parts) == 1:
                # No images were fetched successfully
                return ""

            response = self.gemini_client.models.generate_content(
                model=self.vision_model,
                contents=parts
            )
            return (response.text or "").strip()
        except Exception as e:
            print(f"Image analysis error: {e}")
            return ""

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

    def process_review(self, review_data: dict, history: list = None) -> dict:
        """
        Main entry point for processing a review.
        Orchestrates the analysis pipeline using OpenAI (text) + Gemini (images).
        """
        try:
            # 0. Image Analysis: Analyze any customer photos with Gemini
            image_urls = [
                img.get("image_url")
                for img in (review_data.get("images") or [])
                if img.get("image_url")
            ]
            image_context = self._analyze_images(image_urls)
            if image_context:
                print(f"   [Vision] Analyzed {len(image_urls)} image(s).")

            # 1. Scout: Analyze sentiment and risk
            scout_result = self._scout(review_data, image_context)

            # 2. Translate: Summarize in Vietnamese
            vietnamese_summary = self._translate(review_data, scout_result)

            # 3. Consult: Deep dive if risky
            consult_result = {}
            if scout_result.get('risk_flag'):
                consult_result = self._consult(review_data)

            # 4. Draft: Create a response
            draft_response = self._draft(review_data, scout_result, history, image_context)

            return {
                "scout": scout_result,
                "image_context": image_context,
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

    def _scout(self, review_data: dict, image_context: str = "") -> dict:
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
        if image_context:
            prompt += f"\n\nCustomer photos show: {image_context}"
        
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

    def _draft(self, review_data: dict, scout_result: dict, history_context: list = None, image_context: str = "") -> str:
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

        recent_responses = []
        if history_context and isinstance(history_context[0], dict):
            recent_responses = [
                (item.get("draft_response") or "").strip()
                for item in history_context
                if (item.get("draft_response") or "").strip()
            ]
            recent_reviews_str = self._build_recent_review_context_lines(history_context)
        else:
            recent_responses = [h for h in (history_context or []) if isinstance(h, str) and h.strip()]
            recent_reviews_str = "None."

        history_str = "\n".join([f"- {h}" for h in recent_responses]) if recent_responses else "None."
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
            recent_reviews=recent_reviews_str,
            brand_context=brand_context,
            style_hint=style_hint
        )
        if image_context:
            prompt += f"\n\nCustomer photos show: {image_context}\nIf relevant, you may briefly reference what's visible in the photos (e.g., the nail art, the color choice) to make the response feel more personal."
        
        try:
            recent_openings = self._build_recent_openings(recent_responses)
            recent_closings = self._build_recent_closings(recent_responses)
            attempt_prompt = prompt
            last_draft = ""

            for attempt in range(3):
                draft = self._generate_text(attempt_prompt)
                last_draft = draft
                new_opening = self._normalize_text(self._extract_first_sentence(draft))
                new_closing = self._normalize_text(self._extract_last_sentence(draft))
                starts_with_author_name = self._starts_with_author_name(draft, author)
                opening_repeated = new_opening and new_opening in recent_openings
                closing_repeated = new_closing and new_closing in recent_closings

                token_count = len(self._normalize_text(draft).split())
                similarity_threshold = 0.88 if token_count <= 18 else 0.82
                best_similarity, most_similar = self._find_most_similar_recent(draft, recent_responses)
                too_similar = bool(most_similar) and best_similarity >= similarity_threshold

                if not (opening_repeated or closing_repeated or starts_with_author_name or too_similar):
                    return draft

                if attempt == 2:
                    break

                recent_opening_lines = []
                for h in recent_responses[:10]:
                    first = self._extract_first_sentence(h)
                    if first:
                        recent_opening_lines.append(f"- {first}")

                recent_closing_lines = []
                for h in recent_responses[:10]:
                    last = self._extract_last_sentence(h)
                    if last:
                        recent_closing_lines.append(f"- {last}")

                similarity_note = ""
                if too_similar:
                    similarity_note = (
                        f"\n- Your previous draft is too similar to a recent response (similarity={best_similarity:.2f})."
                        "\n- Use a noticeably different sentence structure and wording."
                        f"\nMost similar recent response:\n- {most_similar}"
                    )

                attempt_prompt = (
                    f"{prompt}\n\nRegenerate with stricter anti-repetition constraints (attempt {attempt + 2}/3):\n"
                    "- Avoid opening with the author's name.\n"
                    "- Use a different opening structure than recent responses.\n"
                    "- Use a different final sentence than recent responses.\n"
                    "- Do not reuse 4+ word sequences from recent responses.\n"
                    f"{similarity_note}\n"
                    "Recent opening lines:\n"
                    + ("\n".join(recent_opening_lines) if recent_opening_lines else "- None.")
                    + "\nRecent closing lines:\n"
                    + ("\n".join(recent_closing_lines) if recent_closing_lines else "- None.")
                )

            return last_draft or "Thank you for your feedback."
        except Exception:
            return "Thank you for your feedback."
