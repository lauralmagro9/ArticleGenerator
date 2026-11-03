"""
Unit tests for db.py

All file system operations are mocked so no real JSON file is created or read.
"""
import json
import pytest
from unittest.mock import patch, mock_open, MagicMock

# ---------------------------------------------------------------------------
# Patch heavy config-level side effects before db is imported
# ---------------------------------------------------------------------------
with (
    patch("config.load_dotenv"),
    patch("config.requests.get") as mock_cat_req,
    patch("os.path.exists", return_value=False),
):
    mock_cat_req.return_value = MagicMock(status_code=200, json=lambda: [])
    import db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_DB = {
    "file-001": {
        "name": "audio.mp3",
        "status": "completed",
        "started_at": "2024-01-01T10:00:00",
        "updated_at": "2024-01-01T10:05:00",
        "completed_at": "2024-01-01T10:05:00",
        "wp_post_id": 42,
        "wp_post_link": "https://example.com/p=42",
    },
    "file-002": {
        "name": "interview.wav",
        "status": "processing",
        "started_at": "2024-01-01T11:00:00",
        "updated_at": "2024-01-01T11:00:00",
    },
    "file-003": {
        "name": "broken.mp3",
        "status": "failed",
        "started_at": "2024-01-01T09:00:00",
        "updated_at": "2024-01-01T09:01:00",
        "error": "Download failed",
    },
}


def _patch_load(return_value=None):
    """Returns a context-manager that patches db.load_db."""
    if return_value is None:
        return_value = {}
    return patch("db.load_db", return_value=return_value)


def _patch_save():
    """Returns a context-manager that patches db.save_db."""
    return patch("db.save_db")


# ===========================================================================
# load_db
# ===========================================================================
class TestLoadDb:
    def test_returns_empty_dict_when_file_missing(self):
        with patch("os.path.exists", return_value=False):
            result = db.load_db()
        assert result == {}

    def test_returns_parsed_json_when_file_exists(self):
        fake_json = json.dumps(SAMPLE_DB)
        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=fake_json)),
        ):
            result = db.load_db()
        assert result == SAMPLE_DB

    def test_returns_empty_dict_on_corrupted_json(self):
        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data="NOT_JSON{")),
        ):
            result = db.load_db()
        assert result == {}

    def test_returns_empty_dict_on_io_error(self):
        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", side_effect=OSError("Permission denied")),
        ):
            result = db.load_db()
        assert result == {}


# ===========================================================================
# save_db
# ===========================================================================
class TestSaveDb:
    def test_writes_json_to_file(self):
        m = mock_open()
        with patch("builtins.open", m):
            db.save_db({"key": "value"})
        # Confirm file was opened for writing
        m.assert_called_once_with(db.DB_FILE, "w", encoding="utf-8")

    def test_handles_io_error_gracefully(self):
        with patch("builtins.open", side_effect=OSError("Disk full")):
            # Should NOT raise; errors are logged only
            db.save_db({"key": "value"})


# ===========================================================================
# is_processed
# ===========================================================================
class TestIsProcessed:
    def test_returns_true_for_completed_file(self):
        with _patch_load(SAMPLE_DB):
            assert db.is_processed("file-001") is True

    def test_returns_false_for_processing_file(self):
        with _patch_load(SAMPLE_DB):
            assert db.is_processed("file-002") is False

    def test_returns_false_for_failed_file(self):
        with _patch_load(SAMPLE_DB):
            assert db.is_processed("file-003") is False

    def test_returns_false_for_unknown_file(self):
        with _patch_load(SAMPLE_DB):
            assert db.is_processed("nonexistent-id") is False

    def test_returns_false_for_empty_db(self):
        with _patch_load({}):
            assert db.is_processed("any-id") is False


# ===========================================================================
# get_file_status
# ===========================================================================
class TestGetFileStatus:
    def test_returns_completed_status(self):
        with _patch_load(SAMPLE_DB):
            assert db.get_file_status("file-001") == "completed"

    def test_returns_processing_status(self):
        with _patch_load(SAMPLE_DB):
            assert db.get_file_status("file-002") == "processing"

    def test_returns_none_for_unknown_file(self):
        with _patch_load(SAMPLE_DB):
            assert db.get_file_status("unknown") is None

    def test_returns_none_for_empty_db(self):
        with _patch_load({}):
            assert db.get_file_status("file-001") is None


# ===========================================================================
# mark_processing
# ===========================================================================
class TestMarkProcessing:
    def test_creates_entry_with_processing_status(self):
        with _patch_load({}) as mock_load, _patch_save() as mock_save:
            db.mark_processing("file-new", "new_audio.mp3")

        saved_data = mock_save.call_args[0][0]
        assert "file-new" in saved_data
        entry = saved_data["file-new"]
        assert entry["status"] == "processing"
        assert entry["name"] == "new_audio.mp3"
        assert "started_at" in entry
        assert "updated_at" in entry

    def test_overwrites_existing_entry(self):
        existing_db = {
            "file-001": {"name": "audio.mp3", "status": "failed"}
        }
        with _patch_load(existing_db), _patch_save() as mock_save:
            db.mark_processing("file-001", "audio.mp3")

        saved_data = mock_save.call_args[0][0]
        assert saved_data["file-001"]["status"] == "processing"


# ===========================================================================
# mark_completed
# ===========================================================================
class TestMarkCompleted:
    def test_updates_status_to_completed(self):
        base_db = {
            "file-002": {
                "name": "interview.wav",
                "status": "processing",
                "started_at": "2024-01-01T11:00:00",
                "updated_at": "2024-01-01T11:00:00",
            }
        }
        with _patch_load(base_db), _patch_save() as mock_save:
            db.mark_completed("file-002", wp_post_id=99, wp_post_link="https://wp.example.com/?p=99")

        saved = mock_save.call_args[0][0]
        entry = saved["file-002"]
        assert entry["status"] == "completed"
        assert entry["wp_post_id"] == 99
        assert entry["wp_post_link"] == "https://wp.example.com/?p=99"
        assert "completed_at" in entry

    def test_does_not_save_when_file_id_unknown(self):
        with _patch_load({}), _patch_save() as mock_save:
            db.mark_completed("nonexistent", 1, "http://x.com")
        mock_save.assert_not_called()


# ===========================================================================
# mark_failed
# ===========================================================================
class TestMarkFailed:
    def test_updates_status_to_failed(self):
        base_db = {
            "file-002": {
                "name": "interview.wav",
                "status": "processing",
                "started_at": "2024-01-01T11:00:00",
                "updated_at": "2024-01-01T11:00:00",
            }
        }
        with _patch_load(base_db), _patch_save() as mock_save:
            db.mark_failed("file-002", "Something went wrong")

        saved = mock_save.call_args[0][0]
        entry = saved["file-002"]
        assert entry["status"] == "failed"
        assert entry["error"] == "Something went wrong"
        assert "failed_at" in entry
        assert "updated_at" in entry

    def test_does_not_save_when_file_id_unknown(self):
        with _patch_load({}), _patch_save() as mock_save:
            db.mark_failed("nonexistent", "error")
        mock_save.assert_not_called()
