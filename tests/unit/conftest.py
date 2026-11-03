"""
Shared pytest fixtures for all test suites.
"""
import json
import os
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Environment / Config fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def suppress_config_side_effects():
    """
    Session-scoped fixture that prevents the config module from making real
    network calls or reading real files during the entire test session.
    """
    with (
        patch("dotenv.load_dotenv"),
        patch("requests.get") as mock_get,
        patch("os.path.exists", return_value=False),
    ):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [])
        yield


@pytest.fixture()
def sample_file_info():
    """A typical Google Drive file info dict."""
    return {"id": "drive-file-001", "name": "podcast_episode.mp3", "mimeType": "audio/mpeg"}


@pytest.fixture()
def sample_article_data():
    """A realistic article dict returned by Gemini."""
    return {
        "title": "10 Tips for Better Python Code",
        "content": "<p>Python is great.</p><h2>Tip 1</h2><p>Use type hints.</p>",
        "metadescription": "Discover 10 actionable tips to write cleaner, faster Python code today.",
        "category": "Technology",
    }


@pytest.fixture()
def sample_db_state():
    """A pre-populated DB dict for tests that need an existing state."""
    return {
        "drive-file-001": {
            "name": "podcast_episode.mp3",
            "status": "completed",
            "started_at": "2024-03-01T08:00:00",
            "completed_at": "2024-03-01T08:05:00",
            "updated_at": "2024-03-01T08:05:00",
            "wp_post_id": 101,
            "wp_post_link": "https://myblog.com/?p=101",
        },
        "drive-file-002": {
            "name": "interview.wav",
            "status": "processing",
            "started_at": "2024-03-01T09:00:00",
            "updated_at": "2024-03-01T09:00:00",
        },
        "drive-file-003": {
            "name": "broken.mp3",
            "status": "failed",
            "error": "Gemini timeout",
            "started_at": "2024-03-01T07:00:00",
            "updated_at": "2024-03-01T07:01:00",
        },
    }


@pytest.fixture()
def tmp_db_file(tmp_path):
    """
    Yields a temporary path for the DB JSON file and patches db.DB_FILE
    to point to it so tests can exercise real file I/O safely.
    """
    db_path = str(tmp_path / "processed_files.json")
    with patch("config.DB_FILE", db_path), patch("db.DB_FILE", db_path):
        yield db_path


@pytest.fixture()
def tmp_audio_file(tmp_path):
    """Creates a tiny fake audio file and returns its path."""
    audio = tmp_path / "sample.mp3"
    audio.write_bytes(b"\xff\xfb\x90\x00" * 100)  # fake MP3 header bytes
    return str(audio)


@pytest.fixture()
def mock_drive_service():
    """Returns a fully configured mock Google Drive API service."""
    service = MagicMock()
    service.files().list().execute.return_value = {"files": []}
    service.files().get_media.return_value = MagicMock()
    return service


@pytest.fixture()
def mock_genai_client(sample_article_data):
    """Returns a mock google.genai.Client pre-configured for a successful run."""
    import json as _json
    client = MagicMock()

    uploaded = MagicMock()
    uploaded.name = "files/mock-upload-xyz"
    client.files.upload.return_value = uploaded

    active_state = MagicMock()
    active_state.state.name = "ACTIVE"
    client.files.get.return_value = active_state

    response = MagicMock()
    response.text = _json.dumps(sample_article_data)
    client.models.generate_content.return_value = response

    return client


@pytest.fixture()
def mock_wp_responses():
    """
    Returns a factory for building mock requests.Response objects for
    WordPress API calls.
    """
    import requests as req_lib

    def _make(status_code=200, json_data=None):
        m = MagicMock()
        m.status_code = status_code
        m.json.return_value = json_data or {}
        m.text = json.dumps(json_data or {})
        if status_code >= 400:
            m.raise_for_status.side_effect = req_lib.exceptions.HTTPError(
                f"HTTP {status_code}", response=m
            )
        else:
            m.raise_for_status.return_value = None
        return m

    return _make
