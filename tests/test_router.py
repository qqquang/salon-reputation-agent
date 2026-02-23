"""Unit tests for IntelligenceRouter pure utility methods.

All OpenAI and Gemini network calls are mocked — these tests exercise
pure Python logic only (text normalization, similarity scoring, sentence
extraction, style-hint building, image-context handling, etc.).
"""
import json
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers to build the router without real API keys
# ---------------------------------------------------------------------------

def _make_router():
    with patch("src.processing.router.OpenAI") as MockOpenAI, \
         patch("src.processing.router.google_genai.Client") as MockGemini:
        MockOpenAI.return_value = MagicMock()
        MockGemini.return_value = MagicMock()
        from src.processing.router import IntelligenceRouter
        r = IntelligenceRouter()
        return r


# ---------------------------------------------------------------------------
# _normalize_text
# ---------------------------------------------------------------------------

class TestNormalizeText:
    def setup_method(self):
        self.r = _make_router()

    def test_lowercases_input(self):
        assert self.r._normalize_text("Hello World") == "hello world"

    def test_strips_punctuation(self):
        assert self.r._normalize_text("Hello, World!") == "hello world"

    def test_collapses_whitespace(self):
        assert self.r._normalize_text("  too   many   spaces  ") == "too many spaces"

    def test_empty_string(self):
        assert self.r._normalize_text("") == ""

    def test_none_input(self):
        assert self.r._normalize_text(None) == ""

    def test_digits_preserved(self):
        assert self.r._normalize_text("Rating 5/5!") == "rating 55"

    def test_mixed_content(self):
        result = self.r._normalize_text("  Great Nails!!! 😀  ")
        assert result == "great nails"


# ---------------------------------------------------------------------------
# _extract_first_sentence / _extract_last_sentence
# ---------------------------------------------------------------------------

class TestSentenceExtraction:
    def setup_method(self):
        self.r = _make_router()

    def test_first_sentence_single(self):
        assert self.r._extract_first_sentence("Hello.") == "Hello."

    def test_first_sentence_multiple(self):
        result = self.r._extract_first_sentence("Hello. How are you? Fine.")
        assert result == "Hello."

    def test_last_sentence_single(self):
        assert self.r._extract_last_sentence("Hello.") == "Hello."

    def test_last_sentence_multiple(self):
        result = self.r._extract_last_sentence("Hello. How are you? Fine.")
        assert result == "Fine."

    def test_empty_string_first(self):
        assert self.r._extract_first_sentence("") == ""

    def test_empty_string_last(self):
        assert self.r._extract_last_sentence("") == ""

    def test_none_first(self):
        assert self.r._extract_first_sentence(None) == ""

    def test_none_last(self):
        assert self.r._extract_last_sentence(None) == ""

    def test_no_punctuation(self):
        # Text with no sentence-ending punctuation returns the whole text
        result = self.r._extract_first_sentence("Just one long sentence without end")
        assert result == "Just one long sentence without end"


# ---------------------------------------------------------------------------
# _starts_with_author_name
# ---------------------------------------------------------------------------

class TestStartsWithAuthorName:
    def setup_method(self):
        self.r = _make_router()

    def test_detects_name_at_start_comma(self):
        assert self.r._starts_with_author_name("Jane, thank you for your review!", "Jane Smith") is True

    def test_detects_name_at_start_space(self):
        assert self.r._starts_with_author_name("Jane thank you for visiting.", "Jane Smith") is True

    def test_no_name_at_start(self):
        assert self.r._starts_with_author_name("Thank you for visiting, Jane!", "Jane Smith") is False

    def test_empty_text(self):
        assert self.r._starts_with_author_name("", "Jane Smith") is False

    def test_empty_author(self):
        assert self.r._starts_with_author_name("Thank you!", "") is False

    def test_none_text(self):
        assert self.r._starts_with_author_name(None, "Jane") is False

    def test_case_insensitive(self):
        assert self.r._starts_with_author_name("jane, thanks!", "Jane Smith") is True


# ---------------------------------------------------------------------------
# _jaccard_similarity
# ---------------------------------------------------------------------------

class TestJaccardSimilarity:
    def setup_method(self):
        self.r = _make_router()

    def test_identical_strings(self):
        assert self.r._jaccard_similarity("hello world", "hello world") == 1.0

    def test_no_overlap(self):
        assert self.r._jaccard_similarity("hello", "world") == 0.0

    def test_partial_overlap(self):
        score = self.r._jaccard_similarity("hello world", "hello there")
        assert 0.0 < score < 1.0

    def test_empty_a(self):
        assert self.r._jaccard_similarity("", "hello") == 0.0

    def test_empty_b(self):
        assert self.r._jaccard_similarity("hello", "") == 0.0

    def test_both_empty(self):
        assert self.r._jaccard_similarity("", "") == 0.0

    def test_symmetry(self):
        a = "the quick brown fox"
        b = "the lazy brown dog"
        assert self.r._jaccard_similarity(a, b) == self.r._jaccard_similarity(b, a)


# ---------------------------------------------------------------------------
# _sentence_overlap_ratio
# ---------------------------------------------------------------------------

class TestSentenceOverlapRatio:
    def setup_method(self):
        self.r = _make_router()

    def test_identical_text(self):
        text = "Thank you for visiting. We hope to see you again."
        assert self.r._sentence_overlap_ratio(text, text) == 1.0

    def test_no_overlap(self):
        a = "Great service today."
        b = "Very disappointed with the experience."
        assert self.r._sentence_overlap_ratio(a, b) == 0.0

    def test_partial_overlap(self):
        a = "Thank you for visiting. Great nails!"
        b = "Thank you for visiting. We hope to see you soon."
        ratio = self.r._sentence_overlap_ratio(a, b)
        # One shared sentence out of two → 0.5
        assert ratio == pytest.approx(0.5)

    def test_empty_strings(self):
        assert self.r._sentence_overlap_ratio("", "") == 0.0

    def test_one_empty(self):
        assert self.r._sentence_overlap_ratio("Hello.", "") == 0.0


# ---------------------------------------------------------------------------
# _similarity_score
# ---------------------------------------------------------------------------

class TestSimilarityScore:
    def setup_method(self):
        self.r = _make_router()

    def test_identical_texts_return_1(self):
        text = "Thank you for your kind feedback!"
        assert self.r._similarity_score(text, text) == pytest.approx(1.0)

    def test_completely_different_returns_low(self):
        score = self.r._similarity_score("hello", "world")
        assert score < 0.5

    def test_empty_strings(self):
        assert self.r._similarity_score("", "") == 0.0

    def test_one_empty(self):
        assert self.r._similarity_score("Hello.", "") == 0.0

    def test_very_similar_texts(self):
        a = "Thank you for your wonderful review!"
        b = "Thank you for your wonderful feedback!"
        score = self.r._similarity_score(a, b)
        assert score > 0.7

    def test_score_bounded_between_0_and_1(self):
        a = "We appreciate your kind words and hope to see you soon."
        b = "We appreciate your feedback and look forward to serving you."
        score = self.r._similarity_score(a, b)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# _find_most_similar_recent
# ---------------------------------------------------------------------------

class TestFindMostSimilarRecent:
    def setup_method(self):
        self.r = _make_router()

    def test_finds_identical_match(self):
        draft = "Thank you for your kind words!"
        history = ["Thank you for your kind words!", "See you again soon."]
        score, match = self.r._find_most_similar_recent(draft, history)
        assert score == pytest.approx(1.0)
        assert match == "Thank you for your kind words!"

    def test_empty_history_returns_zero(self):
        score, match = self.r._find_most_similar_recent("Hello!", [])
        assert score == 0.0
        assert match == ""

    def test_picks_most_similar(self):
        draft = "Thank you for your feedback!"
        history = [
            "We appreciate you visiting.",
            "Thank you for your feedback, it means a lot!",
        ]
        score, match = self.r._find_most_similar_recent(draft, history)
        assert "thank you for your feedback" in match.lower()


# ---------------------------------------------------------------------------
# _build_style_hint
# ---------------------------------------------------------------------------

class TestBuildStyleHint:
    def setup_method(self):
        self.r = _make_router()

    def test_returns_string(self):
        review = {"review_id": "abc", "salon_name": "Mi Nail"}
        hint = self.r._build_style_hint(review, sentiment_score=8, category="Service Quality")
        assert isinstance(hint, str)
        assert len(hint) > 0

    def test_contains_category_and_sentiment(self):
        review = {"review_id": "abc", "salon_name": "Mi Nail"}
        hint = self.r._build_style_hint(review, sentiment_score=8, category="Service Quality")
        assert "Service Quality" in hint
        assert "8" in hint

    def test_low_sentiment_uses_empathy_language(self):
        review = {"review_id": "xyz", "salon_name": "Mi Nail"}
        hint = self.r._build_style_hint(review, sentiment_score=3, category="Complaint")
        # Low-sentiment closing should reference support/resolution
        assert any(word in hint.lower() for word in ["support", "resolution", "private", "accountability", "ownership", "empathy", "concern", "validat"])

    def test_uses_salon_name_in_closing(self):
        # The closing options pool contains two entries with the salon name.
        # Iterate over several review IDs until we find one whose hash selects
        # at least one of the salon-name options — confirming the name is used.
        found = False
        for i in range(30):
            review = {"review_id": f"test-id-{i}", "salon_name": "Fancy Nails"}
            hint = self.r._build_style_hint(review, sentiment_score=9, category="Compliment")
            if "Fancy Nails" in hint:
                found = True
                break
        assert found, "Salon name never appeared in any style hint across 30 review IDs"

    def test_deterministic_for_same_review_id(self):
        review = {"review_id": "deterministic-id", "salon_name": "Mi Nail"}
        hint1 = self.r._build_style_hint(review, 8, "Service")
        hint2 = self.r._build_style_hint(review, 8, "Service")
        assert hint1 == hint2


# ---------------------------------------------------------------------------
# _build_brand_context
# ---------------------------------------------------------------------------

class TestBuildBrandContext:
    def setup_method(self):
        self.r = _make_router()

    def test_empty_brand_context_returns_default(self):
        self.r.brand_context = {}
        result = self.r._build_brand_context()
        assert result == "No additional brand context provided."

    def test_full_brand_context(self):
        self.r.brand_context = {
            "identity": "Premium nail salon",
            "tone": ["warm", "professional"],
            "differentiators": ["organic products"],
            "services": ["manicure", "pedicure"],
            "avoid_phrases": ["no problem"],
        }
        result = self.r._build_brand_context()
        assert "Premium nail salon" in result
        assert "warm" in result
        assert "organic products" in result
        assert "manicure" in result
        assert "no problem" in result

    def test_partial_brand_context(self):
        self.r.brand_context = {"identity": "Local salon"}
        result = self.r._build_brand_context()
        assert "Local salon" in result

    def test_non_dict_brand_context(self):
        self.r.brand_context = None
        result = self.r._build_brand_context()
        assert result == "No additional brand context provided."


# ---------------------------------------------------------------------------
# _build_recent_review_context_lines
# ---------------------------------------------------------------------------

class TestBuildRecentReviewContextLines:
    def setup_method(self):
        self.r = _make_router()

    def test_empty_history(self):
        result = self.r._build_recent_review_context_lines([])
        assert result == "None."

    def test_none_history(self):
        result = self.r._build_recent_review_context_lines(None)
        assert result == "None."

    def test_formats_single_item(self):
        history = [{
            "review_id": "r1",
            "rating": 5,
            "original_text": "Great salon!",
            "draft_response": "Thank you!",
        }]
        result = self.r._build_recent_review_context_lines(history)
        assert "5/5" in result
        assert "Great salon!" in result
        assert "Thank you!" in result

    def test_truncates_long_review_text(self):
        long_text = "x" * 200
        history = [{"rating": 4, "original_text": long_text, "draft_response": "OK"}]
        result = self.r._build_recent_review_context_lines(history)
        assert "..." in result

    def test_placeholder_for_no_text(self):
        history = [{"rating": 3, "original_text": "", "draft_response": ""}]
        result = self.r._build_recent_review_context_lines(history)
        assert "[No review text]" in result
        assert "[No draft response]" in result

    def test_multiple_items(self):
        history = [
            {"rating": 5, "original_text": "Loved it!", "draft_response": "Thanks!"},
            {"rating": 2, "original_text": "Not great.", "draft_response": "Sorry!"},
        ]
        result = self.r._build_recent_review_context_lines(history)
        lines = result.split("\n")
        assert len(lines) == 2


# ---------------------------------------------------------------------------
# _analyze_images (unit — no actual HTTP)
# ---------------------------------------------------------------------------

class TestAnalyzeImages:
    def setup_method(self):
        self.r = _make_router()

    def test_returns_empty_when_no_urls(self):
        self.r.gemini_client = MagicMock()
        result = self.r._analyze_images([])
        assert result == ""

    def test_returns_empty_when_gemini_not_configured(self):
        self.r.gemini_client = None
        result = self.r._analyze_images(["https://example.com/img.jpg"])
        assert result == ""

    def test_filters_none_urls(self):
        self.r.gemini_client = MagicMock()
        result = self.r._analyze_images([None, None])
        assert result == ""

    def test_returns_gemini_text_on_success(self):
        mock_response = MagicMock()
        mock_response.text = "Beautiful manicure with even color application."

        self.r.gemini_client = MagicMock()
        self.r.gemini_client.models.generate_content.return_value = mock_response

        fake_img_response = MagicMock()
        fake_img_response.content = b"fakebytes"
        fake_img_response.headers = {"Content-Type": "image/jpeg"}
        fake_img_response.raise_for_status = MagicMock()

        # requests is imported locally inside _analyze_images — patch at source
        with patch("requests.get", return_value=fake_img_response):
            result = self.r._analyze_images(["https://example.com/img.jpg"])

        assert result == "Beautiful manicure with even color application."

    def test_returns_empty_on_gemini_error(self):
        self.r.gemini_client = MagicMock()
        self.r.gemini_client.models.generate_content.side_effect = Exception("API error")

        fake_img_response = MagicMock()
        fake_img_response.content = b"fakebytes"
        fake_img_response.headers = {"Content-Type": "image/jpeg"}
        fake_img_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=fake_img_response):
            result = self.r._analyze_images(["https://example.com/img.jpg"])

        assert result == ""

    def test_limits_to_5_images(self):
        mock_response = MagicMock()
        mock_response.text = "description"
        self.r.gemini_client = MagicMock()
        self.r.gemini_client.models.generate_content.return_value = mock_response

        fake_img_response = MagicMock()
        fake_img_response.content = b"bytes"
        fake_img_response.headers = {"Content-Type": "image/jpeg"}
        fake_img_response.raise_for_status = MagicMock()

        urls = [f"https://example.com/img{i}.jpg" for i in range(10)]

        with patch("requests.get", return_value=fake_img_response) as mock_get:
            self.r._analyze_images(urls)
            # Only 5 requests should have been made
            assert mock_get.call_count == 5


# ---------------------------------------------------------------------------
# process_review (integration smoke test — all LLM calls mocked)
# ---------------------------------------------------------------------------

class TestProcessReview:
    def setup_method(self):
        self.r = _make_router()

    def _configure_generate_text(self, scout_json=None, translate_text="Bản dịch.", consult_json=None, draft_text="Thank you!"):
        """Configure _generate_text to return sequential responses."""
        scout_payload = scout_json or {"sentiment_score": 8, "risk_flag": False, "category": "Service"}
        consult_payload = consult_json or {}

        responses = iter([
            json.dumps(scout_payload),   # scout
            translate_text,               # translate
            draft_text,                   # draft
        ])
        self.r._generate_text = MagicMock(side_effect=lambda _: next(responses))
        self.r._analyze_images = MagicMock(return_value="")

    def test_returns_expected_keys(self, positive_review):
        self._configure_generate_text()
        result = self.r.process_review(positive_review, [])
        assert "scout" in result
        assert "draft_response" in result
        assert "vietnamese_summary" in result
        assert "processed_at" in result

    def test_scout_values_populated(self, positive_review):
        self._configure_generate_text(scout_json={"sentiment_score": 9, "risk_flag": False, "category": "Compliment"})
        result = self.r.process_review(positive_review, [])
        assert result["scout"]["sentiment_score"] == 9
        assert result["scout"]["risk_flag"] is False

    def test_error_handling_returns_error_key(self, positive_review):
        self.r._scout = MagicMock(side_effect=Exception("boom"))
        result = self.r.process_review(positive_review, [])
        assert "error" in result

    def test_no_text_review_uses_rating_fallback(self, no_text_review):
        # Scout will fail to parse JSON → falls back to rating-based sentiment
        self.r._generate_text = MagicMock(side_effect=Exception("no llm"))
        self.r._analyze_images = MagicMock(return_value="")
        result = self.r.process_review(no_text_review, [])
        # rating 4 → sentiment 8
        assert result.get("scout", {}).get("sentiment_score") == 8

    def test_risk_flag_triggers_consult(self, negative_review):
        scout_payload = {"sentiment_score": 2, "risk_flag": True, "category": "Complaint"}
        consult_payload = {"root_cause": "long wait", "strategy": "apologize"}
        responses = iter([
            json.dumps(scout_payload),
            "Bản dịch.",
            json.dumps(consult_payload),
            "We are sorry for your experience.",
        ])
        self.r._generate_text = MagicMock(side_effect=lambda _: next(responses))
        self.r._analyze_images = MagicMock(return_value="")

        result = self.r.process_review(negative_review, [])
        assert result["consult"] != {}
