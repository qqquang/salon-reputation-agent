"""Shared fixtures for the test suite."""
import os
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Inject minimal env vars so settings and clients don't fail at import."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake-supabase-key")
    monkeypatch.setenv("DRY_RUN", "False")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("VISION_MODEL", "gemini-2.0-flash")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "test@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "testpassword")


# ---------------------------------------------------------------------------
# Review data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def positive_review():
    return {
        "review_id": "rev-001",
        "original_text": "Amazing nail work! The technician was professional and the salon was spotless. Will definitely come back.",
        "rating": 5,
        "author_name": "Jane Smith",
        "salon_name": "Mi Nail",
        "images": [],
    }


@pytest.fixture
def negative_review():
    return {
        "review_id": "rev-002",
        "original_text": "Very disappointed. My nails chipped after one day and the wait time was over an hour.",
        "rating": 1,
        "author_name": "Bob Jones",
        "salon_name": "Mi Nail",
        "images": [],
    }


@pytest.fixture
def no_text_review():
    return {
        "review_id": "rev-003",
        "original_text": "",
        "rating": 4,
        "author_name": "Alice",
        "salon_name": "Mi Nail",
        "images": [],
    }


@pytest.fixture
def review_with_images():
    return {
        "review_id": "rev-004",
        "original_text": "Love the nail art!",
        "rating": 5,
        "author_name": "Carol",
        "salon_name": "Mi Nail",
        "images": [
            {"image_url": "https://example.com/img1.jpg"},
            {"image_url": "https://example.com/img2.jpg"},
        ],
    }


# ---------------------------------------------------------------------------
# History context fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def empty_history():
    return []


@pytest.fixture
def dict_history():
    return [
        {
            "review_id": "rev-100",
            "author_name": "User A",
            "rating": 5,
            "original_text": "Great place!",
            "draft_response": "Thank you for visiting us, we appreciate your kind words!",
        },
        {
            "review_id": "rev-101",
            "author_name": "User B",
            "rating": 4,
            "original_text": "Nice salon.",
            "draft_response": "We are excited to pamper you again soon.",
        },
    ]


# ---------------------------------------------------------------------------
# IntelligenceRouter fixture (mocked OpenAI + Gemini)
# ---------------------------------------------------------------------------

@pytest.fixture
def router(mock_env):
    """Return an IntelligenceRouter with patched OpenAI and Gemini clients."""
    with patch("src.processing.router.OpenAI") as MockOpenAI, \
         patch("src.processing.router.google_genai.Client") as MockGemini:

        mock_openai_instance = MagicMock()
        MockOpenAI.return_value = mock_openai_instance

        mock_gemini_instance = MagicMock()
        MockGemini.return_value = mock_gemini_instance

        from src.processing.router import IntelligenceRouter
        r = IntelligenceRouter()
        r.client = mock_openai_instance
        r.gemini_client = mock_gemini_instance
        # Attach for easy access in tests
        r._mock_openai = mock_openai_instance
        r._mock_gemini = mock_gemini_instance
        yield r
