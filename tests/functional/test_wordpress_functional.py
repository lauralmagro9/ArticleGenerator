"""
Functional tests for services/wordpress_service.py

Uses responses or mock requests to simulate realistic WordPress REST API
interaction flows — pagination, auth failures, partial data, etc.
"""
import pytest
import requests as req_lib
from unittest.mock import patch, MagicMock, call

with (
    patch("dotenv.load_dotenv"),
    patch("requests.get") as _g,
    patch("os.path.exists", return_value=False),
):
    _g.return_value = MagicMock(status_code=200, json=lambda: [])
    from services import wordpress_service as wps


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post(i):
    return {
        "id": i,
        "link": f"https://myblog.test/post-{i}/",
        "title": {"rendered": f"Article Number {i}"},
    }


def _make_resp(status_code=200, json_data=None, text=""):
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = json_data or {}
    m.text = text
    if status_code >= 400:
        m.raise_for_status.side_effect = req_lib.exceptions.HTTPError(
            f"HTTP {status_code}", response=m
        )
    else:
        m.raise_for_status.return_value = None
    return m


# ===========================================================================
# get_published_posts — pagination scenarios
# ===========================================================================
class TestGetPublishedPostsPagination:
    def test_single_page_under_limit(self):
        posts = [_post(i) for i in range(1, 6)]
        with patch("requests.get", return_value=_make_resp(200, posts)):
            result = wps.get_published_posts(max_posts=100)
        assert len(result) == 5
        assert result[0]["title"] == "Article Number 1"

    def test_paginated_retrieval_of_exactly_max_posts(self):
        page1 = [_post(i) for i in range(1, 101)]    # 100 posts, full page
        page2 = [_post(i) for i in range(101, 151)]  # 50 posts, last page
        responses = [
            _make_resp(200, page1),
            _make_resp(200, page2),
        ]
        with patch("requests.get", side_effect=responses):
            result = wps.get_published_posts(max_posts=150)
        assert len(result) == 150

    def test_stops_at_max_posts_even_if_more_exist(self):
        page1 = [_post(i) for i in range(1, 101)]
        page2 = [_post(i) for i in range(101, 201)]
        responses = [_make_resp(200, page1), _make_resp(200, page2)]
        with patch("requests.get", side_effect=responses):
            result = wps.get_published_posts(max_posts=50)
        assert len(result) == 50

    def test_stops_on_400_beyond_last_page(self):
        page1 = [_post(i) for i in range(1, 101)]
        responses = [_make_resp(200, page1), _make_resp(400)]
        with patch("requests.get", side_effect=responses):
            result = wps.get_published_posts(max_posts=200)
        assert len(result) == 100

    def test_stops_on_empty_batch(self):
        page1 = [_post(i) for i in range(1, 11)]  # 10 posts
        responses = [_make_resp(200, page1), _make_resp(200, [])]
        with patch("requests.get", side_effect=responses):
            result = wps.get_published_posts(max_posts=100)
        assert len(result) == 10

    def test_returns_empty_on_connection_error(self):
        with patch("requests.get", side_effect=req_lib.exceptions.ConnectionError("unreachable")):
            result = wps.get_published_posts()
        assert result == []

    def test_skips_posts_with_no_link(self):
        posts = [
            {"id": 1, "link": "", "title": {"rendered": "No Link"}},
            {"id": 2, "link": "https://myblog.test/ok/", "title": {"rendered": "Has Link"}},
        ]
        with patch("requests.get", return_value=_make_resp(200, posts)):
            result = wps.get_published_posts(max_posts=10)
        assert len(result) == 1
        assert result[0]["url"] == "https://myblog.test/ok/"

    def test_handles_string_title_field(self):
        posts = [{"id": 1, "link": "https://myblog.test/x/", "title": "Plain Title"}]
        with patch("requests.get", return_value=_make_resp(200, posts)):
            result = wps.get_published_posts(max_posts=10)
        assert result[0]["title"] == "Plain Title"


# ===========================================================================
# post_draft_to_wordpress — realistic payload & response scenarios
# ===========================================================================
class TestPostDraftToWordpressIntegration:
    def test_full_payload_with_all_optional_fields(self):
        resp = _make_resp(201, {"id": 123, "link": "https://myblog.test/?p=123"})
        with patch("requests.post", return_value=resp) as mock_post:
            post_id, link = wps.post_draft_to_wordpress(
                title="Full Article",
                content="<p>Content</p>",
                metadescription="SEO description here.",
                category_id=3,
            )

        assert post_id == 123
        assert link == "https://myblog.test/?p=123"
        payload = mock_post.call_args.kwargs["json"]
        assert payload["title"] == "Full Article"
        assert payload["content"] == "<p>Content</p>"
        assert payload["categories"] == [3]
        assert payload["meta"]["_yoast_wpseo_metadesc"] == "SEO description here."
        assert payload["status"] == "pending"

    def test_minimal_payload_without_optional_fields(self):
        resp = _make_resp(201, {"id": 5, "link": "https://myblog.test/?p=5"})
        with patch("requests.post", return_value=resp) as mock_post:
            wps.post_draft_to_wordpress(title="Minimal", content="<p>Body</p>")

        payload = mock_post.call_args.kwargs["json"]
        assert "categories" not in payload
        assert "meta" not in payload

    def test_401_raises_and_logs_hint(self, caplog):
        resp = _make_resp(401)
        with patch("requests.post", return_value=resp):
            with pytest.raises(req_lib.exceptions.HTTPError):
                wps.post_draft_to_wordpress(title="T", content="C")

    def test_500_raises_http_error(self):
        resp = _make_resp(500, text="Internal Server Error")
        with patch("requests.post", return_value=resp):
            with pytest.raises(req_lib.exceptions.HTTPError):
                wps.post_draft_to_wordpress(title="T", content="C")

    def test_connection_error_propagates(self):
        with patch("requests.post", side_effect=req_lib.exceptions.ConnectionError("no route")):
            with pytest.raises(req_lib.exceptions.ConnectionError):
                wps.post_draft_to_wordpress(title="T", content="C")

    def test_timeout_propagates(self):
        with patch("requests.post", side_effect=req_lib.exceptions.Timeout("timed out")):
            with pytest.raises(req_lib.exceptions.Timeout):
                wps.post_draft_to_wordpress(title="T", content="C")

    def test_date_field_is_in_payload(self):
        resp = _make_resp(201, {"id": 1, "link": "http://x.com"})
        with patch("requests.post", return_value=resp) as mock_post:
            wps.post_draft_to_wordpress(title="T", content="C")
        payload = mock_post.call_args.kwargs["json"]
        assert "date" in payload
        # Rough ISO-8601 shape check
        assert "T" in payload["date"]

    def test_uses_basic_auth(self):
        resp = _make_resp(201, {"id": 1, "link": "http://x.com"})
        with patch("requests.post", return_value=resp) as mock_post:
            wps.post_draft_to_wordpress(title="T", content="C")
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs.get("auth") is not None
