"""Unit tests for DataForSEOClient.

All HTTP calls are mocked with unittest.mock — no real network access.
Tests cover:
  - Header generation
  - Retry logic (_request_json)
  - Response parsing (_make_request)
  - fetch_reviews polling loop
  - search_businesses happy path
"""
import pytest
import requests as req_lib
from unittest.mock import patch, MagicMock, call


def _make_client():
    from src.ingestion.dataforseo import DataForSEOClient
    return DataForSEOClient()


def _json_response(status_code=20000, tasks=None):
    """Build a DataForSEO-shaped JSON response dict."""
    return {
        "status_code": status_code,
        "status_message": "Ok.",
        "tasks": tasks or [],
    }


# ---------------------------------------------------------------------------
# _get_headers
# ---------------------------------------------------------------------------

class TestGetHeaders:
    def test_authorization_header_present(self):
        client = _make_client()
        headers = client._get_headers()
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Basic ")

    def test_content_type_is_json(self):
        client = _make_client()
        headers = client._get_headers()
        assert headers["Content-Type"] == "application/json"

    def test_credentials_encoded_correctly(self):
        from base64 import b64decode
        client = _make_client()
        headers = client._get_headers()
        encoded = headers["Authorization"].replace("Basic ", "")
        decoded = b64decode(encoded).decode("utf-8")
        assert decoded == f"{client.login}:{client.password}"


# ---------------------------------------------------------------------------
# _request_json — retry logic
# ---------------------------------------------------------------------------

class TestRequestJsonRetry:
    def test_success_on_first_attempt(self):
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"status_code": 20000}

        with patch("src.ingestion.dataforseo.requests.post", return_value=mock_resp) as mock_post:
            result = client._request_json("POST", "https://api.example.com", [{"key": "val"}])

        assert result == {"status_code": 20000}
        assert mock_post.call_count == 1

    def test_retries_on_request_exception(self):
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"status_code": 20000}

        with patch("src.ingestion.dataforseo.requests.post") as mock_post, \
             patch("src.ingestion.dataforseo.time.sleep"):
            mock_post.side_effect = [req_lib.RequestException("timeout"), mock_resp]
            result = client._request_json("POST", "https://api.example.com", [])

        assert mock_post.call_count == 2
        assert result == {"status_code": 20000}

    def test_raises_after_max_retries(self):
        client = _make_client()

        with patch("src.ingestion.dataforseo.requests.post") as mock_post, \
             patch("src.ingestion.dataforseo.time.sleep"):
            mock_post.side_effect = req_lib.RequestException("persistent error")
            with pytest.raises(req_lib.RequestException):
                client._request_json("POST", "https://api.example.com", [])

        assert mock_post.call_count == client.REQUEST_RETRIES

    def test_get_method_uses_requests_get(self):
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"status_code": 20000}

        with patch("src.ingestion.dataforseo.requests.get", return_value=mock_resp) as mock_get:
            result = client._request_json("GET", "https://api.example.com/task/123")

        assert mock_get.call_count == 1
        assert result == {"status_code": 20000}

    def test_exponential_backoff_between_retries(self):
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"ok": True}
        sleep_calls = []

        with patch("src.ingestion.dataforseo.requests.post") as mock_post, \
             patch("src.ingestion.dataforseo.time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            mock_post.side_effect = [req_lib.RequestException("err"), mock_resp]
            client._request_json("POST", "https://api.example.com", [])

        # First retry waits 2^0 = 1 second
        assert sleep_calls[0] == 1


# ---------------------------------------------------------------------------
# _make_request — response parsing
# ---------------------------------------------------------------------------

class TestMakeRequest:
    def test_returns_items_on_success(self):
        client = _make_client()
        items = [{"id_review": "r1"}, {"id_review": "r2"}]
        response = _json_response(tasks=[{
            "status_code": 20000,
            "result": [{"items": items}]
        }])

        with patch.object(client, "_request_json", return_value=response):
            result = client._make_request("https://api.example.com/reviews", [{}])

        assert result == items

    def test_returns_task_id_when_is_task_post(self):
        client = _make_client()
        task_id = "abc-123"
        response = _json_response(tasks=[{
            "status_code": 20100,
            "id": task_id,
        }])

        with patch.object(client, "_request_json", return_value=response):
            result = client._make_request("https://api.example.com/task_post", [{}], is_task_post=True)

        assert result == task_id

    def test_returns_none_on_top_level_api_error(self):
        client = _make_client()
        response = _json_response(status_code=40000)

        with patch.object(client, "_request_json", return_value=response):
            result = client._make_request("https://api.example.com/task_post", [{}], is_task_post=True)

        assert result is None

    def test_returns_empty_list_on_top_level_error_non_task_post(self):
        client = _make_client()
        response = _json_response(status_code=40000)

        with patch.object(client, "_request_json", return_value=response):
            result = client._make_request("https://api.example.com/reviews", [{}])

        assert result == []

    def test_returns_none_on_exception_task_post(self):
        client = _make_client()
        with patch.object(client, "_request_json", side_effect=Exception("crash")):
            result = client._make_request("https://api.example.com/task_post", [{}], is_task_post=True)
        assert result is None

    def test_returns_empty_list_on_exception_non_task_post(self):
        client = _make_client()
        with patch.object(client, "_request_json", side_effect=Exception("crash")):
            result = client._make_request("https://api.example.com/reviews", [{}])
        assert result == []


# ---------------------------------------------------------------------------
# fetch_reviews — async polling
# ---------------------------------------------------------------------------

class TestFetchReviews:
    def test_returns_items_and_title_on_success(self):
        client = _make_client()
        task_id = "task-001"
        items = [{"id_review": "r1", "rating": {"value": 5}}]

        poll_response = _json_response(tasks=[{
            "status_code": 20000,
            "result": [{"items": items, "title": "Mi Nail Salon"}]
        }])

        with patch.object(client, "_make_request", return_value=task_id), \
             patch.object(client, "_request_json", return_value=poll_response), \
             patch("src.ingestion.dataforseo.time.sleep"):
            reviews, title = client.fetch_reviews("12345", depth=10)

        assert reviews == items
        assert title == "Mi Nail Salon"

    def test_returns_empty_when_task_post_fails(self):
        client = _make_client()
        with patch.object(client, "_make_request", return_value=None):
            reviews, title = client.fetch_reviews("12345")
        assert reviews == []
        assert title is None

    def test_returns_empty_on_task_not_found(self):
        client = _make_client()
        task_id = "task-002"

        not_found_response = _json_response(tasks=[{
            "status_code": 40400,
        }])

        with patch.object(client, "_make_request", return_value=task_id), \
             patch.object(client, "_request_json", return_value=not_found_response), \
             patch("src.ingestion.dataforseo.time.sleep"):
            reviews, title = client.fetch_reviews("99999")

        assert reviews == []
        assert title is None

    def test_timeout_after_max_polls(self):
        client = _make_client()
        task_id = "task-003"

        # Status 10100 = "in queue" — never completes
        running_response = _json_response(tasks=[{"status_code": 10100}])

        sleep_calls = []
        with patch.object(client, "_make_request", return_value=task_id), \
             patch.object(client, "_request_json", return_value=running_response), \
             patch("src.ingestion.dataforseo.time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            reviews, title = client.fetch_reviews("12345")

        # Should have polled 30 times and timed out
        assert len(sleep_calls) == 30
        assert reviews == []
        assert title is None

    def test_handles_poll_exception_gracefully(self):
        client = _make_client()
        task_id = "task-004"
        items = [{"id_review": "r1"}]

        # First poll raises, second poll succeeds
        success_response = _json_response(tasks=[{
            "status_code": 20000,
            "result": [{"items": items, "title": "Salon"}]
        }])

        poll_side_effects = [Exception("network blip"), success_response]

        with patch.object(client, "_make_request", return_value=task_id), \
             patch.object(client, "_request_json", side_effect=poll_side_effects), \
             patch("src.ingestion.dataforseo.time.sleep"):
            reviews, title = client.fetch_reviews("12345")

        assert reviews == items


# ---------------------------------------------------------------------------
# search_businesses
# ---------------------------------------------------------------------------

class TestSearchBusinesses:
    def test_returns_items_on_success(self):
        client = _make_client()
        items = [{"cid": "111", "title": "Best Nails"}]

        with patch.object(client, "_make_request", return_value=items) as mock_req:
            result = client.search_businesses("nail salon near me")

        assert result == items
        # Verify the correct endpoint is called
        called_url = mock_req.call_args[0][0]
        assert "maps/live/advanced" in called_url

    def test_passes_keyword_in_payload(self):
        client = _make_client()
        with patch.object(client, "_make_request", return_value=[]) as mock_req:
            client.search_businesses("gel nails")

        payload = mock_req.call_args[0][1]
        assert payload[0]["keyword"] == "gel nails"

    def test_returns_empty_list_on_failure(self):
        client = _make_client()
        with patch.object(client, "_make_request", return_value=[]):
            result = client.search_businesses("anything")
        assert result == []
