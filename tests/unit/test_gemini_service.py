"""
Unit tests for services/gemini_service.py

The google.genai client is fully mocked so no real API calls are made.
"""
import json
import pytest
from unittest.mock import patch, MagicMock, call

# ---------------------------------------------------------------------------
# Patch config side-effects before importing the service
# ---------------------------------------------------------------------------
with (
    patch("dotenv.load_dotenv"),
    patch("requests.get") as _mock_get,
    patch("os.path.exists", return_value=False),
):
    _mock_get.return_value = MagicMock(status_code=200, json=lambda: [])
    from services import gemini_service as gs


# ===========================================================================
# Helpers
# ===========================================================================

VALID_ARTICLE = {
    "title": "Great Podcast Recap",
    "content": "<p>Summary of the show.</p>",
    "metadescription": "A 130-char meta description for the article covering key topics.",
    "category": "Technology",
}


def _make_client(file_state="ACTIVE", response_json=None):
    """Returns a mock genai.Client with all needed sub-mocks configured."""
    if response_json is None:
        response_json = VALID_ARTICLE

    client = MagicMock()

    # files.upload → uploaded_file
    uploaded_file = MagicMock()
    uploaded_file.name = "files/test-abc123"
    client.files.upload.return_value = uploaded_file

    # files.get → file_info with .state
    file_info = MagicMock()
    file_info.state.name = file_state
    client.files.get.return_value = file_info

    # models.generate_content → response with .text
    response = MagicMock()
    response.text = json.dumps(response_json)
    client.models.generate_content.return_value = response

    return client, uploaded_file


# ===========================================================================
# generate_article_from_audio
# ===========================================================================
class TestGenerateArticleFromAudio:
    def _call(self, client, local_path="/tmp/audio.mp3", related_articles=None):
        with patch("google.genai.Client", return_value=client):
            return gs.generate_article_from_audio(local_path, related_articles=related_articles)

    def test_returns_dict_with_expected_keys(self):
        client, _ = _make_client()
        result = self._call(client)
        assert set(result.keys()) == {"title", "content", "metadescription", "category"}

    def test_returns_correct_title_and_content(self):
        client, _ = _make_client()
        result = self._call(client)
        assert result["title"] == VALID_ARTICLE["title"]
        assert result["content"] == VALID_ARTICLE["content"]

    def test_uploads_correct_local_file(self):
        client, _ = _make_client()
        self._call(client, local_path="/tmp/my_audio.mp3")
        client.files.upload.assert_called_once_with(file="/tmp/my_audio.mp3")

    def test_polls_until_active(self):
        client, uploaded_file = _make_client(file_state="ACTIVE")
        # First call returns PROCESSING, second returns ACTIVE
        processing = MagicMock()
        processing.state.name = "PROCESSING"
        active = MagicMock()
        active.state.name = "ACTIVE"
        client.files.get.side_effect = [processing, active]

        with patch("time.sleep"):
            result = self._call(client)

        assert client.files.get.call_count == 2
        assert result["title"] == VALID_ARTICLE["title"]

    def test_raises_when_file_state_is_failed(self):
        client, uploaded_file = _make_client(file_state="FAILED")
        failed = MagicMock()
        failed.state.name = "FAILED"
        client.files.get.return_value = failed

        with pytest.raises(Exception, match="processing failed"):
            self._call(client)

    def test_deletes_uploaded_file_on_success(self):
        client, uploaded_file = _make_client()
        self._call(client)
        client.files.delete.assert_called_once_with(name=uploaded_file.name)

    def test_deletes_uploaded_file_on_exception(self):
        client, uploaded_file = _make_client()
        client.models.generate_content.side_effect = RuntimeError("Model error")

        with pytest.raises(RuntimeError):
            self._call(client)

        client.files.delete.assert_called_once_with(name=uploaded_file.name)

    def test_raises_on_invalid_json_response(self):
        client, _ = _make_client()
        client.models.generate_content.return_value.text = "NOT_VALID_JSON"

        with pytest.raises(json.JSONDecodeError):
            self._call(client)

    def test_related_articles_injected_into_prompt(self):
        client, _ = _make_client()
        articles = [
            {"title": "Intro to Python", "url": "https://blog.test/intro-python/"},
            {"title": "Advanced Tips", "url": "https://blog.test/advanced/"},
        ]
        with patch("google.genai.Client", return_value=client):
            gs.generate_article_from_audio("/tmp/a.mp3", related_articles=articles)

        # Check the prompt passed to generate_content contains the article URLs
        contents_arg = client.models.generate_content.call_args.kwargs.get(
            "contents"
        ) or client.models.generate_content.call_args[0][0]
        # The prompt is the second element: [uploaded_file, prompt_string]
        prompt_str = contents_arg[1] if isinstance(contents_arg, (list, tuple)) else str(contents_arg)
        assert "https://blog.test/intro-python/" in prompt_str
        assert "https://blog.test/advanced/" in prompt_str

    def test_no_related_articles_uses_fallback_text(self):
        client, _ = _make_client()
        with patch("google.genai.Client", return_value=client):
            gs.generate_article_from_audio("/tmp/a.mp3", related_articles=None)

        contents_arg = client.models.generate_content.call_args.kwargs.get(
            "contents"
        ) or client.models.generate_content.call_args[0][0]
        prompt_str = contents_arg[1] if isinstance(contents_arg, (list, tuple)) else str(contents_arg)
        assert "No hay publicaciones anteriores" in prompt_str

    def test_uses_untitled_fallback_when_title_missing(self):
        article_no_title = {**VALID_ARTICLE, "title": None}
        client, _ = _make_client(response_json=article_no_title)
        # Patch json.loads to return dict without title
        with patch("google.genai.Client", return_value=client):
            result = gs.generate_article_from_audio("/tmp/a.mp3")
        assert result["title"] == "Untitled Article"
