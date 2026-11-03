"""
Unit tests for main.py

All external dependencies (db, google_drive_service, gemini_service,
wordpress_service, config) are mocked.
"""
import os
import pytest
from unittest.mock import patch, MagicMock, call

# ---------------------------------------------------------------------------
# Patch heavy config side effects before importing main
# ---------------------------------------------------------------------------
with (
    patch("dotenv.load_dotenv"),
    patch("requests.get") as _mock_get,
    patch("os.path.exists", return_value=False),
):
    _mock_get.return_value = MagicMock(status_code=200, json=lambda: [])
    import main


# ===========================================================================
# Helpers / shared patches
# ===========================================================================

FILE_INFO = {"id": "file-abc", "name": "episode.mp3"}

ARTICLE_DATA = {
    "title": "Episode Title",
    "content": "<p>Body text</p>",
    "metadescription": "A short description.",
    "category": "Technology",
}


def _patch_all(
    download_path="/tmp/episode.mp3",
    article_data=None,
    wp_result=(42, "https://wp.test/?p=42"),
    categories_map=None,
    is_processed_return=False,
    audio_files=None,
    published_posts=None,
):
    """Returns a dict of mock patches for the main module's collaborators."""
    if article_data is None:
        article_data = ARTICLE_DATA
    if categories_map is None:
        categories_map = {"Technology": 5}
    if audio_files is None:
        audio_files = [FILE_INFO]
    if published_posts is None:
        published_posts = []

    patches = {
        "db.mark_processing": patch("main.db.mark_processing"),
        "db.mark_completed": patch("main.db.mark_completed"),
        "db.mark_failed": patch("main.db.mark_failed"),
        "db.is_processed": patch("main.db.is_processed", return_value=is_processed_return),
        "google_drive_service.download_file": patch(
            "main.google_drive_service.download_file", return_value=download_path
        ),
        "google_drive_service.list_audio_files": patch(
            "main.google_drive_service.list_audio_files", return_value=audio_files
        ),
        "gemini_service.generate_article_from_audio": patch(
            "main.gemini_service.generate_article_from_audio", return_value=article_data
        ),
        "wordpress_service.post_draft_to_wordpress": patch(
            "main.wordpress_service.post_draft_to_wordpress", return_value=wp_result
        ),
        "wordpress_service.get_published_posts": patch(
            "main.wordpress_service.get_published_posts", return_value=published_posts
        ),
        "config.CATEGORIES_MAP": patch.dict("main.config.CATEGORIES_MAP", categories_map, clear=True),
        "os.path.exists": patch("main.os.path.exists", return_value=True),
        "os.remove": patch("main.os.remove"),
    }
    return patches


# ===========================================================================
# clean_local_file
# ===========================================================================
class TestCleanLocalFile:
    def test_removes_file_when_it_exists(self):
        with patch("main.os.path.exists", return_value=True), \
             patch("main.os.remove") as mock_remove:
            main.clean_local_file("/tmp/audio.mp3")
        mock_remove.assert_called_once_with("/tmp/audio.mp3")

    def test_does_nothing_when_file_does_not_exist(self):
        with patch("main.os.path.exists", return_value=False), \
             patch("main.os.remove") as mock_remove:
            main.clean_local_file("/tmp/audio.mp3")
        mock_remove.assert_not_called()

    def test_does_nothing_when_path_is_none(self):
        with patch("main.os.remove") as mock_remove:
            main.clean_local_file(None)
        mock_remove.assert_not_called()

    def test_does_nothing_when_path_is_empty_string(self):
        with patch("main.os.remove") as mock_remove:
            main.clean_local_file("")
        mock_remove.assert_not_called()

    def test_handles_os_error_gracefully(self):
        with patch("main.os.path.exists", return_value=True), \
             patch("main.os.remove", side_effect=PermissionError("denied")):
            # Should not raise
            main.clean_local_file("/tmp/audio.mp3")


# ===========================================================================
# process_file
# ===========================================================================
class TestProcessFile:
    def test_full_happy_path(self):
        patches = _patch_all()
        with (
            patches["db.mark_processing"] as mock_mark_proc,
            patches["db.mark_completed"] as mock_mark_done,
            patches["db.mark_failed"],
            patches["google_drive_service.download_file"],
            patches["gemini_service.generate_article_from_audio"],
            patches["wordpress_service.post_draft_to_wordpress"] as mock_wp,
            patches["config.CATEGORIES_MAP"],
            patches["os.path.exists"],
            patches["os.remove"],
        ):
            main.process_file(FILE_INFO)

        mock_mark_proc.assert_called_once_with("file-abc", "episode.mp3")
        mock_mark_done.assert_called_once_with("file-abc", 42, "https://wp.test/?p=42")

    def test_marks_failed_when_download_returns_none(self):
        patches = _patch_all(download_path=None)
        with (
            patches["db.mark_processing"],
            patches["db.mark_completed"] as mock_done,
            patches["db.mark_failed"] as mock_failed,
            patches["google_drive_service.download_file"],
            patches["config.CATEGORIES_MAP"],
        ):
            main.process_file(FILE_INFO)

        mock_failed.assert_called_once()
        mock_done.assert_not_called()

    def test_marks_failed_when_gemini_raises(self):
        patches = _patch_all()
        with (
            patches["db.mark_processing"],
            patches["db.mark_completed"] as mock_done,
            patches["db.mark_failed"] as mock_failed,
            patches["google_drive_service.download_file"],
            patch("main.gemini_service.generate_article_from_audio",
                  side_effect=RuntimeError("Gemini error")),
            patches["config.CATEGORIES_MAP"],
            patches["os.path.exists"],
            patches["os.remove"],
        ):
            main.process_file(FILE_INFO)

        mock_failed.assert_called_once()
        assert "Gemini error" in mock_failed.call_args[0][1]
        mock_done.assert_not_called()

    def test_marks_failed_when_gemini_returns_empty_title(self):
        bad_article = {**ARTICLE_DATA, "title": None}
        patches = _patch_all(article_data=bad_article)
        with (
            patches["db.mark_processing"],
            patches["db.mark_completed"] as mock_done,
            patches["db.mark_failed"] as mock_failed,
            patches["google_drive_service.download_file"],
            patches["gemini_service.generate_article_from_audio"],
            patches["config.CATEGORIES_MAP"],
            patches["os.path.exists"],
            patches["os.remove"],
        ):
            main.process_file(FILE_INFO)

        mock_failed.assert_called_once()
        mock_done.assert_not_called()

    def test_marks_failed_when_wordpress_raises(self):
        patches = _patch_all()
        import requests as req_lib
        with (
            patches["db.mark_processing"],
            patches["db.mark_completed"] as mock_done,
            patches["db.mark_failed"] as mock_failed,
            patches["google_drive_service.download_file"],
            patches["gemini_service.generate_article_from_audio"],
            patch("main.wordpress_service.post_draft_to_wordpress",
                  side_effect=req_lib.exceptions.HTTPError("WP 500")),
            patches["config.CATEGORIES_MAP"],
            patches["os.path.exists"],
            patches["os.remove"],
        ):
            main.process_file(FILE_INFO)

        mock_failed.assert_called_once()
        mock_done.assert_not_called()

    def test_always_cleans_local_file(self):
        """Even when processing fails, the temp file must be cleaned up."""
        patches = _patch_all()
        with (
            patches["db.mark_processing"],
            patches["db.mark_completed"],
            patches["db.mark_failed"],
            patches["google_drive_service.download_file"],
            patch("main.gemini_service.generate_article_from_audio",
                  side_effect=RuntimeError("boom")),
            patches["config.CATEGORIES_MAP"],
            patches["os.path.exists"],
            patches["os.remove"] as mock_remove,
        ):
            main.process_file(FILE_INFO)

        mock_remove.assert_called_once_with("/tmp/episode.mp3")

    def test_maps_category_name_to_id(self):
        article = {**ARTICLE_DATA, "category": "Technology"}
        patches = _patch_all(article_data=article, categories_map={"Technology": 7})
        with (
            patches["db.mark_processing"],
            patches["db.mark_completed"],
            patches["db.mark_failed"],
            patches["google_drive_service.download_file"],
            patches["gemini_service.generate_article_from_audio"],
            patches["wordpress_service.post_draft_to_wordpress"] as mock_wp,
            patches["config.CATEGORIES_MAP"],
            patches["os.path.exists"],
            patches["os.remove"],
        ):
            main.process_file(FILE_INFO)

        call_kwargs = mock_wp.call_args.kwargs
        assert call_kwargs.get("category_id") == 7

    def test_maps_category_case_insensitively(self):
        article = {**ARTICLE_DATA, "category": "technology"}
        patches = _patch_all(article_data=article, categories_map={"Technology": 7})
        with (
            patches["db.mark_processing"],
            patches["db.mark_completed"],
            patches["db.mark_failed"],
            patches["google_drive_service.download_file"],
            patches["gemini_service.generate_article_from_audio"],
            patches["wordpress_service.post_draft_to_wordpress"] as mock_wp,
            patches["config.CATEGORIES_MAP"],
            patches["os.path.exists"],
            patches["os.remove"],
        ):
            main.process_file(FILE_INFO)

        call_kwargs = mock_wp.call_args.kwargs
        assert call_kwargs.get("category_id") == 7


# ===========================================================================
# check_and_process
# ===========================================================================
class TestCheckAndProcess:
    def test_skips_already_processed_files(self):
        patches = _patch_all(is_processed_return=True)
        with (
            patches["google_drive_service.list_audio_files"],
            patches["db.is_processed"],
            patches["wordpress_service.get_published_posts"],
            patch("main.process_file") as mock_process_file,
        ):
            main.check_and_process()

        mock_process_file.assert_not_called()

    def test_processes_new_files(self):
        patches = _patch_all(is_processed_return=False)
        with (
            patches["google_drive_service.list_audio_files"],
            patches["db.is_processed"],
            patches["wordpress_service.get_published_posts"],
            patch("main.process_file") as mock_process_file,
        ):
            main.check_and_process()

        mock_process_file.assert_called_once_with(FILE_INFO, related_articles=[])

    def test_returns_early_when_no_audio_files(self):
        with (
            patch("main.google_drive_service.list_audio_files", return_value=[]),
            patch("main.process_file") as mock_pf,
        ):
            main.check_and_process()
        mock_pf.assert_not_called()

    def test_passes_published_posts_to_process_file(self):
        pub_posts = [{"title": "Old Post", "url": "https://wp.test/old/"}]
        with (
            patch("main.google_drive_service.list_audio_files", return_value=[FILE_INFO]),
            patch("main.db.is_processed", return_value=False),
            patch("main.wordpress_service.get_published_posts", return_value=pub_posts),
            patch("main.process_file") as mock_pf,
        ):
            main.check_and_process()

        mock_pf.assert_called_once_with(FILE_INFO, related_articles=pub_posts)
