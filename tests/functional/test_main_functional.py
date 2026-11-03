"""
Functional tests for main.py

End-to-end orchestration flows — all external services are mocked, but the
real function call-chains (process_file, check_and_process) are exercised.
"""
import pytest
from unittest.mock import patch, MagicMock, call

with (
    patch("dotenv.load_dotenv"),
    patch("requests.get") as _g,
    patch("os.path.exists", return_value=False),
):
    _g.return_value = MagicMock(status_code=200, json=lambda: [])
    import main


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

ARTICLE = {
    "title": "Great Episode Recap",
    "content": "<p>Detailed body.</p>",
    "metadescription": "A 130-char meta description about the podcast episode content here.",
    "category": "Technology",
}

FILE_1 = {"id": "f1", "name": "ep1.mp3"}
FILE_2 = {"id": "f2", "name": "ep2.mp3"}


def _services(
    audio_files=None,
    is_processed_map=None,
    download_path="/tmp/ep.mp3",
    article=None,
    wp_result=(10, "https://wp.test/?p=10"),
    published_posts=None,
    categories_map=None,
    drive_raises=None,
    gemini_raises=None,
    wp_raises=None,
):
    """
    Context-manager factory that stubs all main.py collaborators.
    Returns a dict of mock objects so callers can assert on them.
    """
    if audio_files is None:
        audio_files = [FILE_1]
    if is_processed_map is None:
        is_processed_map = {}
    if article is None:
        article = ARTICLE
    if published_posts is None:
        published_posts = []
    if categories_map is None:
        categories_map = {"Technology": 3}

    mocks = {}

    class _CM:
        def __enter__(self_):
            self_._patches = [
                patch("main.google_drive_service.list_audio_files",
                      return_value=audio_files),
                patch("main.db.is_processed",
                      side_effect=lambda fid: is_processed_map.get(fid, False)),
                patch("main.wordpress_service.get_published_posts",
                      return_value=published_posts),
                patch("main.google_drive_service.download_file",
                      side_effect=drive_raises or (lambda *a, **kw: download_path)),
                patch("main.gemini_service.generate_article_from_audio",
                      side_effect=gemini_raises or (lambda *a, **kw: article)),
                patch("main.wordpress_service.post_draft_to_wordpress",
                      side_effect=wp_raises or (lambda **kw: wp_result)),
                patch("main.db.mark_processing"),
                patch("main.db.mark_completed"),
                patch("main.db.mark_failed"),
                patch.dict("main.config.CATEGORIES_MAP", categories_map, clear=True),
                patch("main.os.path.exists", return_value=True),
                patch("main.os.remove"),
            ]
            started = [p.start() for p in self_._patches]
            mocks["list_audio"] = started[0]
            mocks["is_processed"] = started[1]
            mocks["get_posts"] = started[2]
            mocks["download"] = started[3]
            mocks["gemini"] = started[4]
            mocks["wp_post"] = started[5]
            mocks["mark_proc"] = started[6]
            mocks["mark_done"] = started[7]
            mocks["mark_fail"] = started[8]
            mocks["os_remove"] = started[10]
            return mocks

        def __exit__(self_, *args):
            for p in self_._patches:
                p.stop()

    return _CM()


# ===========================================================================
# process_file — orchestration correctness
# ===========================================================================
class TestProcessFileOrchestration:
    def test_happy_path_calls_all_services_in_order(self):
        with _services() as m:
            main.process_file(FILE_1)

        m["mark_proc"].assert_called_once_with("f1", "ep1.mp3")
        m["gemini"].assert_called_once()
        m["wp_post"].assert_called_once()
        m["mark_done"].assert_called_once_with("f1", 10, "https://wp.test/?p=10")
        m["mark_fail"].assert_not_called()

    def test_temp_file_cleaned_up_on_success(self):
        with _services() as m:
            main.process_file(FILE_1)
        m["os_remove"].assert_called_once_with("/tmp/ep.mp3")

    def test_temp_file_cleaned_up_on_gemini_failure(self):
        with _services(gemini_raises=RuntimeError("API down")) as m:
            main.process_file(FILE_1)
        m["os_remove"].assert_called_once_with("/tmp/ep.mp3")
        m["mark_fail"].assert_called_once()
        m["mark_done"].assert_not_called()

    def test_download_failure_skips_gemini_and_wp(self):
        with _services(download_path=None) as m:
            main.process_file(FILE_1)
        m["gemini"].assert_not_called()
        m["wp_post"].assert_not_called()
        m["mark_fail"].assert_called_once()

    def test_wp_failure_marks_file_as_failed(self):
        import requests as req_lib
        with _services(wp_raises=req_lib.exceptions.HTTPError("WP 500")) as m:
            main.process_file(FILE_1)
        m["mark_fail"].assert_called_once()
        m["mark_done"].assert_not_called()

    def test_empty_title_marks_as_failed(self):
        bad = {**ARTICLE, "title": ""}
        with _services(article=bad) as m:
            main.process_file(FILE_1)
        m["mark_fail"].assert_called_once()

    def test_none_content_marks_as_failed(self):
        bad = {**ARTICLE, "content": None}
        with _services(article=bad) as m:
            main.process_file(FILE_1)
        m["mark_fail"].assert_called_once()

    def test_category_mapped_to_id_correctly(self):
        with _services(categories_map={"Technology": 99}) as m:
            main.process_file(FILE_1)
        call_kwargs = m["wp_post"].call_args.kwargs
        assert call_kwargs["category_id"] == 99

    def test_unknown_category_passes_none_to_wordpress(self):
        article = {**ARTICLE, "category": "UnknownCategory"}
        with _services(article=article, categories_map={"Technology": 3}) as m:
            main.process_file(FILE_1)
        call_kwargs = m["wp_post"].call_args.kwargs
        assert call_kwargs["category_id"] is None

    def test_related_articles_forwarded_to_gemini(self):
        posts = [{"title": "Old Post", "url": "https://blog.test/old/"}]
        with _services() as m:
            main.process_file(FILE_1, related_articles=posts)
        call_kwargs = m["gemini"].call_args.kwargs
        assert call_kwargs["related_articles"] == posts


# ===========================================================================
# check_and_process — full pipeline
# ===========================================================================
class TestCheckAndProcessPipeline:
    def test_processes_only_unprocessed_files(self):
        files = [FILE_1, FILE_2]
        is_processed = {"f1": True, "f2": False}  # f1 already done

        with _services(audio_files=files, is_processed_map=is_processed) as m:
            main.check_and_process()

        # Only f2 should have been processed
        proc_call_ids = [c.args[0] for c in m["mark_proc"].call_args_list]
        assert "f1" not in proc_call_ids
        assert "f2" in proc_call_ids

    def test_all_files_already_processed_runs_nothing(self):
        files = [FILE_1, FILE_2]
        is_processed = {"f1": True, "f2": True}

        with _services(audio_files=files, is_processed_map=is_processed) as m:
            main.check_and_process()

        m["mark_proc"].assert_not_called()
        m["gemini"].assert_not_called()

    def test_no_audio_files_returns_early(self):
        with _services(audio_files=[]) as m:
            main.check_and_process()

        m["get_posts"].assert_not_called()
        m["gemini"].assert_not_called()

    def test_published_posts_passed_to_each_process_file(self):
        posts = [
            {"title": "A", "url": "https://blog.test/a/"},
            {"title": "B", "url": "https://blog.test/b/"},
        ]
        files = [FILE_1, FILE_2]

        with _services(audio_files=files, published_posts=posts) as m:
            main.check_and_process()

        # Both files processed, each received the same posts list
        gemini_calls = m["gemini"].call_args_list
        assert len(gemini_calls) == 2
        for c in gemini_calls:
            assert c.kwargs["related_articles"] == posts

    def test_one_file_failure_does_not_prevent_next(self):
        """If file-1 fails, file-2 must still be attempted."""
        files = [FILE_1, FILE_2]
        call_count = {"n": 0}

        def gemini_side_effect(*a, **kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("First file failed")
            return ARTICLE

        with _services(audio_files=files, gemini_raises=None) as m:
            m["gemini"].side_effect = gemini_side_effect
            main.check_and_process()

        assert m["mark_fail"].call_count == 1
        assert m["mark_done"].call_count == 1

    def test_fetches_published_posts_once_for_whole_batch(self):
        files = [FILE_1, FILE_2]
        with _services(audio_files=files) as m:
            main.check_and_process()
        m["get_posts"].assert_called_once()


# ===========================================================================
# clean_local_file — integrated with real os calls
# ===========================================================================
class TestCleanLocalFileIntegrated:
    def test_removes_existing_file(self, tmp_audio_file):
        import os
        assert os.path.exists(tmp_audio_file)
        main.clean_local_file(tmp_audio_file)
        assert not os.path.exists(tmp_audio_file)

    def test_no_error_on_already_deleted_file(self, tmp_audio_file):
        import os
        os.remove(tmp_audio_file)
        # Should not raise even though file is gone
        main.clean_local_file(tmp_audio_file)

    def test_no_error_on_none(self):
        main.clean_local_file(None)

    def test_no_error_on_empty_string(self):
        main.clean_local_file("")
