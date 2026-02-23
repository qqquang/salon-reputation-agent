"""Unit tests for supabase_client helpers.

Focused on the pure-Python `append_history_context` helper which has no
external dependencies and represents the highest-value testable logic in
that module.
"""
import pytest
from unittest.mock import patch, MagicMock


# We import through the module so monkeypatching of settings works
def get_helper():
    from src.db.supabase_client import append_history_context
    return append_history_context


# ---------------------------------------------------------------------------
# append_history_context — core de-duplication and rolling-window logic
# ---------------------------------------------------------------------------

class TestAppendHistoryContext:

    def test_adds_new_entry_to_empty_list(self):
        fn = get_helper()
        result = fn([], "r1", {"author_name": "Alice", "rating": 5, "original_text": "Great!"}, "Thank you!")
        assert len(result) == 1
        assert result[0]["review_id"] == "r1"

    def test_adds_new_entry_to_existing_list(self):
        fn = get_helper()
        existing = [{"review_id": "r0", "author_name": "Bob", "rating": 4, "original_text": "Nice.", "draft_response": "Thanks!"}]
        result = fn(existing, "r1", {"author_name": "Alice", "rating": 5, "original_text": "Great!"}, "Wonderful!")
        assert len(result) == 2
        assert result[0]["review_id"] == "r1"  # newest first

    def test_deduplicates_existing_review_id(self):
        fn = get_helper()
        existing = [{"review_id": "r1", "author_name": "Alice", "rating": 4, "original_text": "Old text.", "draft_response": "Old draft."}]
        result = fn(existing, "r1", {"author_name": "Alice", "rating": 5, "original_text": "Updated text."}, "New draft.")
        # Should only have one entry for r1
        ids = [item["review_id"] for item in result]
        assert ids.count("r1") == 1
        # Should reflect the new data
        assert result[0]["original_text"] == "Updated text."
        assert result[0]["draft_response"] == "New draft."

    def test_new_entry_is_prepended(self):
        fn = get_helper()
        existing = [{"review_id": "r-old", "author_name": "X", "rating": 3, "original_text": "Meh.", "draft_response": "OK."}]
        result = fn(existing, "r-new", {"author_name": "Y", "rating": 5, "original_text": "Wow!"}, "Amazing!")
        assert result[0]["review_id"] == "r-new"

    def test_enforces_limit(self):
        fn = get_helper()
        history = [
            {"review_id": f"r{i}", "author_name": "X", "rating": 5, "original_text": ".", "draft_response": "."}
            for i in range(20)
        ]
        result = fn(history, "new", {"author_name": "Z", "rating": 5, "original_text": "New"}, "Draft", limit=20)
        assert len(result) == 20

    def test_respects_custom_limit(self):
        fn = get_helper()
        history = [
            {"review_id": f"r{i}", "author_name": "X", "rating": 5, "original_text": ".", "draft_response": "."}
            for i in range(5)
        ]
        result = fn(history, "new", {"author_name": "Z", "rating": 5, "original_text": "New"}, "Draft", limit=3)
        assert len(result) == 3

    def test_none_history_treated_as_empty(self):
        fn = get_helper()
        result = fn(None, "r1", {"author_name": "Alice", "rating": 5, "original_text": "Good"}, "Thanks!")
        assert len(result) == 1
        assert result[0]["review_id"] == "r1"

    def test_none_review_id_still_inserts(self):
        fn = get_helper()
        # review_id=None: no de-duplication filter applied, entry still inserted
        result = fn([], None, {"author_name": "Alice", "rating": 5, "original_text": "Good"}, "Thanks!")
        assert len(result) == 1
        assert result[0]["review_id"] is None

    def test_fields_are_correctly_stored(self):
        fn = get_helper()
        review_data = {"author_name": "Jane", "rating": 4, "original_text": "Lovely place."}
        result = fn([], "r42", review_data, "We appreciate your visit!")
        entry = result[0]
        assert entry["review_id"] == "r42"
        assert entry["author_name"] == "Jane"
        assert entry["rating"] == 4
        assert entry["original_text"] == "Lovely place."
        assert entry["draft_response"] == "We appreciate your visit!"

    def test_original_list_not_mutated_after_call(self):
        fn = get_helper()
        original = [{"review_id": "r0", "author_name": "A", "rating": 5, "original_text": ".", "draft_response": "."}]
        original_copy = list(original)
        fn(original, "r1", {"author_name": "B", "rating": 4, "original_text": "."}, "Draft.")
        # The original list should not be mutated (new list is returned)
        assert original == original_copy

    def test_draft_response_can_be_none(self):
        fn = get_helper()
        result = fn([], "r1", {"author_name": "Alice", "rating": 5, "original_text": "Great!"}, None)
        assert result[0]["draft_response"] is None


# ---------------------------------------------------------------------------
# SupabaseClient DRY_RUN behaviour
# ---------------------------------------------------------------------------

class TestSupabaseClientDryRun:
    """Verify that DRY_RUN mode short-circuits all DB operations safely."""

    def _get_fresh_client(self, monkeypatch):
        """Force a fresh SupabaseClient singleton for each test."""
        monkeypatch.setenv("DRY_RUN", "True")
        # Reset singleton between tests
        import src.db.supabase_client as sc_module
        sc_module.SupabaseClient._instance = None
        from importlib import reload
        import config.settings as settings_mod
        reload(settings_mod)
        reload(sc_module)
        return sc_module.SupabaseClient()

    def test_review_exists_returns_false_in_dry_run(self, monkeypatch):
        client = self._get_fresh_client(monkeypatch)
        assert client.review_exists("any-id") is False

    def test_get_recent_responses_returns_empty_in_dry_run(self, monkeypatch):
        client = self._get_fresh_client(monkeypatch)
        assert client.get_recent_responses() == []

    def test_get_recent_review_context_returns_empty_in_dry_run(self, monkeypatch):
        client = self._get_fresh_client(monkeypatch)
        assert client.get_recent_review_context() == []

    def test_get_salon_name_returns_none_in_dry_run(self, monkeypatch):
        client = self._get_fresh_client(monkeypatch)
        assert client.get_salon_name("any-cid") is None

    def test_insert_review_does_not_raise_in_dry_run(self, monkeypatch, capsys):
        client = self._get_fresh_client(monkeypatch)
        # Should not raise; just prints
        client.insert_review({"review_id": "test-id", "status": "ANALYZED"})
        captured = capsys.readouterr()
        assert "DRY_RUN" in captured.out

    def test_update_status_does_not_raise_in_dry_run(self, monkeypatch, capsys):
        client = self._get_fresh_client(monkeypatch)
        client.update_status("test-id", "ANALYZED")
        captured = capsys.readouterr()
        assert "DRY_RUN" in captured.out
