"""
Functional tests for db.py

These tests exercise the real file-system behaviour by writing to and
reading from a temporary JSON file, validating the full read-write cycle.
"""
import json
import os
import pytest
import db
from unittest.mock import patch


# ===========================================================================
# Full round-trip: mark_processing → mark_completed
# ===========================================================================
class TestDbRoundTripCompleted:
    def test_file_progresses_from_processing_to_completed(self, tmp_db_file):
        file_id = "drive-abc-001"
        file_name = "episode_1.mp3"

        # 1. Mark as processing
        db.mark_processing(file_id, file_name)

        # Verify intermediate state on disk
        with open(tmp_db_file, "r") as f:
            state = json.load(f)
        assert state[file_id]["status"] == "processing"
        assert state[file_id]["name"] == file_name

        # 2. Mark as completed
        db.mark_completed(file_id, wp_post_id=55, wp_post_link="https://blog.test/?p=55")

        # Verify final state on disk
        with open(tmp_db_file, "r") as f:
            state = json.load(f)

        entry = state[file_id]
        assert entry["status"] == "completed"
        assert entry["wp_post_id"] == 55
        assert entry["wp_post_link"] == "https://blog.test/?p=55"
        assert "completed_at" in entry
        assert "updated_at" in entry

    def test_is_processed_returns_true_after_completion(self, tmp_db_file):
        file_id = "drive-abc-002"
        db.mark_processing(file_id, "ep2.mp3")
        db.mark_completed(file_id, 10, "https://blog.test/?p=10")
        assert db.is_processed(file_id) is True

    def test_is_processed_returns_false_while_processing(self, tmp_db_file):
        file_id = "drive-abc-003"
        db.mark_processing(file_id, "ep3.mp3")
        assert db.is_processed(file_id) is False


# ===========================================================================
# Full round-trip: mark_processing → mark_failed
# ===========================================================================
class TestDbRoundTripFailed:
    def test_file_progresses_from_processing_to_failed(self, tmp_db_file):
        file_id = "drive-fail-001"
        db.mark_processing(file_id, "broken.mp3")
        db.mark_failed(file_id, "Network timeout")

        with open(tmp_db_file, "r") as f:
            state = json.load(f)

        entry = state[file_id]
        assert entry["status"] == "failed"
        assert entry["error"] == "Network timeout"
        assert "failed_at" in entry

    def test_is_processed_returns_false_after_failure(self, tmp_db_file):
        file_id = "drive-fail-002"
        db.mark_processing(file_id, "bad.mp3")
        db.mark_failed(file_id, "API error")
        assert db.is_processed(file_id) is False

    def test_get_file_status_returns_failed(self, tmp_db_file):
        file_id = "drive-fail-003"
        db.mark_processing(file_id, "fail3.mp3")
        db.mark_failed(file_id, "crash")
        assert db.get_file_status(file_id) == "failed"


# ===========================================================================
# Multiple files coexist in the DB
# ===========================================================================
class TestDbMultipleFiles:
    def test_multiple_files_tracked_independently(self, tmp_db_file):
        db.mark_processing("f1", "file1.mp3")
        db.mark_processing("f2", "file2.mp3")
        db.mark_completed("f1", 1, "https://blog.test/?p=1")
        db.mark_failed("f2", "error")

        assert db.is_processed("f1") is True
        assert db.is_processed("f2") is False
        assert db.get_file_status("f1") == "completed"
        assert db.get_file_status("f2") == "failed"

    def test_existing_entries_not_overwritten_by_new_entry(self, tmp_db_file):
        db.mark_processing("stable", "stable.mp3")
        db.mark_completed("stable", 99, "https://blog.test/?p=99")

        # Add a second file — stable entry must remain untouched
        db.mark_processing("new-file", "new.mp3")

        assert db.is_processed("stable") is True
        assert db.get_file_status("new-file") == "processing"


# ===========================================================================
# Edge cases on an empty or absent DB file
# ===========================================================================
class TestDbEdgeCases:
    def test_mark_completed_on_unknown_id_does_not_crash(self, tmp_db_file):
        db.mark_completed("never-existed", 1, "https://x.com")
        # No entry should be written
        if os.path.exists(tmp_db_file):
            with open(tmp_db_file, "r") as f:
                state = json.load(f)
            assert "never-existed" not in state

    def test_mark_failed_on_unknown_id_does_not_crash(self, tmp_db_file):
        db.mark_failed("never-existed", "oops")
        if os.path.exists(tmp_db_file):
            with open(tmp_db_file, "r") as f:
                state = json.load(f)
            assert "never-existed" not in state

    def test_load_db_returns_empty_when_file_absent(self, tmp_db_file):
        # tmp_db_file doesn't exist yet at this point
        assert db.load_db() == {}

    def test_get_file_status_returns_none_for_unknown_id(self, tmp_db_file):
        assert db.get_file_status("ghost-id") is None
