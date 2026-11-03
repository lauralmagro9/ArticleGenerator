"""
Unit tests for services/wordpress_service.py

All HTTP calls (requests.get / requests.post) are mocked.
"""
import pytest
import requests as req_lib
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
    from services import wordpress_service as wps


def _mock_response(status_code=200, json_data=None):
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = json_data or {}
    if status_code >= 400:
        m.raise_for_status.side_effect = req_lib.exceptions.HTTPError(
            f"{status_code} Error", response=m
        )
    else:
        m.raise_for_status.return_value = None
    return m


# ===========================================================================
# get_published_posts
# ===========================================================================
class TestGetPublishedPosts:
    def test_returns_list_of_title_url_dicts(self):
        batch = [
            {"id": 1, "link": "https://wp.test/post-1/", "title": {"rendered": "Post One"}},
            {"id": 2, "link": "https://wp.test/post-2/", "title": {"rendered": "Post Two"}},
        ]
        with patch("requests.get", return_value=_mock_response(200, batch)):
            result = wps.get_published_posts(max_posts=10)

        assert len(result) == 2
        assert result[0] == {"title": "Post One", "url": "https://wp.test/post-1/"}
        assert result[1] == {"title": "Post Two", "url": "https://wp.test/post-2/"}

    def test_returns_empty_list_when_no_posts(self):
        with patch("requests.get", return_value=_mock_response(200, [])):
            result = wps.get_published_posts()
        assert result == []

    def test_stops_pagination_on_400(self):
        responses = [
            _mock_response(200, [{"id": i, "link": f"https://wp.test/p{i}/",
                                   "title": {"rendered": f"Post {i}"}} for i in range(1, 101)]),
            _mock_response(400),
        ]
        with patch("requests.get", side_effect=responses):
            result = wps.get_published_posts(max_posts=200)
        assert len(result) == 100

    def test_stops_on_fewer_results_than_per_page(self):
        """If batch < per_page we know we're on the last page."""
        small_batch = [
            {"id": 1, "link": "https://wp.test/only/", "title": {"rendered": "Only Post"}}
        ]
        with patch("requests.get", return_value=_mock_response(200, small_batch)):
            result = wps.get_published_posts(max_posts=100)
        assert len(result) == 1

    def test_handles_plain_string_title(self):
        batch = [{"id": 1, "link": "https://wp.test/x/", "title": "Simple Title"}]
        with patch("requests.get", return_value=_mock_response(200, batch)):
            result = wps.get_published_posts(max_posts=10)
        assert result[0]["title"] == "Simple Title"

    def test_skips_post_with_missing_url(self):
        batch = [
            {"id": 1, "link": "", "title": {"rendered": "No URL"}},
            {"id": 2, "link": "https://wp.test/ok/", "title": {"rendered": "Has URL"}},
        ]
        with patch("requests.get", return_value=_mock_response(200, batch)):
            result = wps.get_published_posts(max_posts=10)
        assert len(result) == 1
        assert result[0]["title"] == "Has URL"

    def test_returns_empty_list_on_request_exception(self):
        with patch("requests.get", side_effect=req_lib.exceptions.ConnectionError("down")):
            result = wps.get_published_posts()
        assert result == []

    def test_respects_max_posts_limit(self):
        batch = [
            {"id": i, "link": f"https://wp.test/p{i}/", "title": {"rendered": f"Post {i}"}}
            for i in range(1, 101)
        ]
        with patch("requests.get", return_value=_mock_response(200, batch)):
            result = wps.get_published_posts(max_posts=5)
        assert len(result) == 5


# ===========================================================================
# post_draft_to_wordpress
# ===========================================================================
class TestPostDraftToWordpress:
    def test_returns_post_id_and_link_on_success(self):
        fake_response_data = {"id": 77, "link": "https://wp.test/?p=77"}
        with patch("requests.post", return_value=_mock_response(201, fake_response_data)):
            post_id, post_link = wps.post_draft_to_wordpress(
                title="My Article",
                content="<p>Content here</p>",
            )
        assert post_id == 77
        assert post_link == "https://wp.test/?p=77"

    def test_includes_category_in_payload_when_provided(self):
        fake_response = _mock_response(201, {"id": 1, "link": "http://x.com"})
        with patch("requests.post", return_value=fake_response) as mock_post:
            wps.post_draft_to_wordpress(
                title="T", content="C", category_id=5
            )
        payload = mock_post.call_args.kwargs["json"]
        assert payload["categories"] == [5]

    def test_omits_category_from_payload_when_none(self):
        fake_response = _mock_response(201, {"id": 1, "link": "http://x.com"})
        with patch("requests.post", return_value=fake_response) as mock_post:
            wps.post_draft_to_wordpress(title="T", content="C")
        payload = mock_post.call_args.kwargs["json"]
        assert "categories" not in payload

    def test_includes_metadescription_in_meta_when_provided(self):
        fake_response = _mock_response(201, {"id": 1, "link": "http://x.com"})
        with patch("requests.post", return_value=fake_response) as mock_post:
            wps.post_draft_to_wordpress(
                title="T", content="C", metadescription="SEO description"
            )
        payload = mock_post.call_args.kwargs["json"]
        assert payload["meta"]["_yoast_wpseo_metadesc"] == "SEO description"

    def test_raises_on_401_unauthorized(self):
        with patch("requests.post", return_value=_mock_response(401)):
            with pytest.raises(req_lib.exceptions.HTTPError):
                wps.post_draft_to_wordpress(title="T", content="C")

    def test_raises_on_500_server_error(self):
        with patch("requests.post", return_value=_mock_response(500)):
            with pytest.raises(req_lib.exceptions.HTTPError):
                wps.post_draft_to_wordpress(title="T", content="C")

    def test_raises_on_connection_error(self):
        with patch("requests.post", side_effect=req_lib.exceptions.ConnectionError("down")):
            with pytest.raises(req_lib.exceptions.ConnectionError):
                wps.post_draft_to_wordpress(title="T", content="C")

    def test_status_is_pending(self):
        fake_response = _mock_response(201, {"id": 1, "link": "http://x.com"})
        with patch("requests.post", return_value=fake_response) as mock_post:
            wps.post_draft_to_wordpress(title="T", content="C")
        payload = mock_post.call_args.kwargs["json"]
        assert payload["status"] == "pending"
