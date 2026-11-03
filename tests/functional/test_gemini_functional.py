"""
Functional tests for services/gemini_service.py

Validates the full article-generation flow — upload, polling loop, prompt
construction, response parsing, and mandatory cleanup — using a mock client.
"""
import json
import time
import pytest
from unittest.mock import patch, MagicMock, call

with (
    patch("dotenv.load_dotenv"),
    patch("requests.get") as _g,
    patch("os.path.exists", return_value=False),
):
    _g.return_value = MagicMock(status_code=200, json=lambda: [])
    from services import gemini_service as gs


VALID_ARTICLE = {
    "title": "Mastering FastAPI",
    "content": "<p>FastAPI is fast.</p>",
    "metadescription": "Learn FastAPI essentials in this comprehensive guide under 150 chars.",
    "category": "Technology",
}


def _build_client(states=None, response_json=None, upload_raises=None, generate_raises=None):
    """
    Factory for a mock genai.Client.

    Args:
        states: list of state strings for successive files.get() calls.
                Defaults to ['ACTIVE'].
        response_json: dict to serialize as response.text.
        upload_raises: exception to raise from files.upload.
        generate_raises: exception to raise from models.generate_content.
    """
    if states is None:
        states = ["ACTIVE"]
    if response_json is None:
        response_json = VALID_ARTICLE

    client = MagicMock()

    uploaded = MagicMock()
    uploaded.name = "files/functional-test-001"

    if upload_raises:
        client.files.upload.side_effect = upload_raises
    else:
        client.files.upload.return_value = uploaded

    def _get_side_effect(name):
        fi = MagicMock()
        fi.state.name = states.pop(0) if states else "ACTIVE"
        return fi

    client.files.get.side_effect = _get_side_effect

    if generate_raises:
        client.models.generate_content.side_effect = generate_raises
    else:
        response = MagicMock()
        response.text = json.dumps(response_json)
        client.models.generate_content.return_value = response

    return client, uploaded


# ===========================================================================
# Full happy-path flow
# ===========================================================================
class TestGenerateArticleHappyPath:
    def test_returns_all_four_fields(self, tmp_audio_file):
        client, _ = _build_client()
        with patch("google.genai.Client", return_value=client):
            result = gs.generate_article_from_audio(tmp_audio_file)

        assert result["title"] == VALID_ARTICLE["title"]
        assert result["content"] == VALID_ARTICLE["content"]
        assert result["metadescription"] == VALID_ARTICLE["metadescription"]
        assert result["category"] == VALID_ARTICLE["category"]

    def test_uploads_the_given_file_path(self, tmp_audio_file):
        client, _ = _build_client()
        with patch("google.genai.Client", return_value=client):
            gs.generate_article_from_audio(tmp_audio_file)
        client.files.upload.assert_called_once_with(file=tmp_audio_file)

    def test_deletes_file_from_gemini_storage_after_success(self, tmp_audio_file):
        client, uploaded = _build_client()
        with patch("google.genai.Client", return_value=client):
            gs.generate_article_from_audio(tmp_audio_file)
        client.files.delete.assert_called_once_with(name=uploaded.name)

    def test_structured_json_response_mode_requested(self, tmp_audio_file):
        client, _ = _build_client()
        with patch("google.genai.Client", return_value=client):
            gs.generate_article_from_audio(tmp_audio_file)

        config_arg = client.models.generate_content.call_args.kwargs.get("config")
        assert config_arg is not None
        assert config_arg.response_mime_type == "application/json"


# ===========================================================================
# Polling loop behaviour
# ===========================================================================
class TestPollingLoop:
    def test_waits_for_processing_then_continues(self, tmp_audio_file):
        """Client must poll until ACTIVE even if file starts PROCESSING."""
        client, _ = _build_client(states=["PROCESSING", "PROCESSING", "ACTIVE"])
        with (
            patch("google.genai.Client", return_value=client),
            patch("time.sleep") as mock_sleep,
        ):
            result = gs.generate_article_from_audio(tmp_audio_file)

        assert client.files.get.call_count == 3
        assert mock_sleep.call_count == 2  # sleeps between each non-ACTIVE poll
        assert result["title"] == VALID_ARTICLE["title"]

    def test_raises_immediately_on_failed_state(self, tmp_audio_file):
        client, _ = _build_client(states=["FAILED"])
        with (
            patch("google.genai.Client", return_value=client),
            patch("time.sleep"),
        ):
            with pytest.raises(Exception, match="processing failed"):
                gs.generate_article_from_audio(tmp_audio_file)

    def test_cleanup_called_even_after_failed_state(self, tmp_audio_file):
        client, uploaded = _build_client(states=["FAILED"])
        with (
            patch("google.genai.Client", return_value=client),
            patch("time.sleep"),
        ):
            with pytest.raises(Exception):
                gs.generate_article_from_audio(tmp_audio_file)
        client.files.delete.assert_called_once_with(name=uploaded.name)


# ===========================================================================
# Prompt construction
# ===========================================================================
class TestPromptConstruction:
    def test_related_articles_appear_as_html_links_in_prompt(self, tmp_audio_file):
        client, _ = _build_client()
        articles = [
            {"title": "Python Basics", "url": "https://blog.test/python-basics/"},
            {"title": "Advanced Python", "url": "https://blog.test/advanced/"},
        ]
        with patch("google.genai.Client", return_value=client):
            gs.generate_article_from_audio(tmp_audio_file, related_articles=articles)

        contents = client.models.generate_content.call_args.kwargs.get("contents") \
                   or client.models.generate_content.call_args[0][0]
        prompt = contents[1]
        assert "https://blog.test/python-basics/" in prompt
        assert "Python Basics" in prompt
        assert "https://blog.test/advanced/" in prompt

    def test_no_articles_uses_spanish_fallback(self, tmp_audio_file):
        client, _ = _build_client()
        with patch("google.genai.Client", return_value=client):
            gs.generate_article_from_audio(tmp_audio_file, related_articles=None)

        contents = client.models.generate_content.call_args.kwargs.get("contents") \
                   or client.models.generate_content.call_args[0][0]
        prompt = contents[1]
        assert "No hay publicaciones anteriores" in prompt

    def test_empty_articles_list_uses_fallback(self, tmp_audio_file):
        client, _ = _build_client()
        with patch("google.genai.Client", return_value=client):
            gs.generate_article_from_audio(tmp_audio_file, related_articles=[])

        contents = client.models.generate_content.call_args.kwargs.get("contents") \
                   or client.models.generate_content.call_args[0][0]
        prompt = contents[1]
        assert "No hay publicaciones anteriores" in prompt


# ===========================================================================
# Error handling & cleanup
# ===========================================================================
class TestErrorHandlingAndCleanup:
    def test_raises_json_decode_error_on_invalid_response(self, tmp_audio_file):
        client, _ = _build_client()
        client.models.generate_content.return_value.text = "{broken json"
        with patch("google.genai.Client", return_value=client):
            with pytest.raises(json.JSONDecodeError):
                gs.generate_article_from_audio(tmp_audio_file)

    def test_cleanup_called_on_json_decode_error(self, tmp_audio_file):
        client, uploaded = _build_client()
        client.models.generate_content.return_value.text = "{bad}"
        with patch("google.genai.Client", return_value=client):
            with pytest.raises(Exception):
                gs.generate_article_from_audio(tmp_audio_file)
        client.files.delete.assert_called_once_with(name=uploaded.name)

    def test_raises_on_upload_failure(self, tmp_audio_file):
        client, _ = _build_client(upload_raises=IOError("S3 upload failed"))
        with patch("google.genai.Client", return_value=client):
            with pytest.raises(IOError):
                gs.generate_article_from_audio(tmp_audio_file)

    def test_no_cleanup_when_upload_itself_failed(self, tmp_audio_file):
        """If upload fails, uploaded_file is None — delete must NOT be called."""
        client, _ = _build_client(upload_raises=IOError("upload error"))
        with patch("google.genai.Client", return_value=client):
            with pytest.raises(IOError):
                gs.generate_article_from_audio(tmp_audio_file)
        client.files.delete.assert_not_called()

    def test_title_fallback_when_missing_in_response(self, tmp_audio_file):
        partial = {**VALID_ARTICLE, "title": None}
        client, _ = _build_client(response_json=partial)
        with patch("google.genai.Client", return_value=client):
            result = gs.generate_article_from_audio(tmp_audio_file)
        assert result["title"] == "Untitled Article"

    def test_cleanup_survives_delete_exception(self, tmp_audio_file):
        """A failure in file cleanup must NOT mask the actual return value."""
        client, uploaded = _build_client()
        client.files.delete.side_effect = Exception("delete failed")
        with patch("google.genai.Client", return_value=client):
            result = gs.generate_article_from_audio(tmp_audio_file)
        # Should still return a valid result despite cleanup failure
        assert result["title"] == VALID_ARTICLE["title"]
