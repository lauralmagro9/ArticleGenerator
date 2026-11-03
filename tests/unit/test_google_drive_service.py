"""
Unit tests for services/google_drive_service.py

Google Drive API clients, credentials, and all I/O are mocked.
"""
import io
import os
import pytest
from unittest.mock import patch, MagicMock, call

# ---------------------------------------------------------------------------
# Suppress module-level config side effects before importing the service
# ---------------------------------------------------------------------------
with (
    patch("dotenv.load_dotenv"),
    patch("requests.get") as _mock_get,
    patch("os.path.exists", return_value=False),
    patch("google.oauth2.service_account.Credentials.from_service_account_file"),
    patch("googleapiclient.discovery.build"),
):
    _mock_get.return_value = MagicMock(status_code=200, json=lambda: [])
    from services import google_drive_service as gds


# ===========================================================================
# is_audio_file
# ===========================================================================
class TestIsAudioFile:
    @pytest.mark.parametrize("mime_type", [
        "audio/mpeg", "audio/wav", "audio/ogg", "audio/mp4",
    ])
    def test_returns_true_for_audio_mime_types(self, mime_type):
        assert gds.is_audio_file({"name": "file.bin", "mimeType": mime_type}) is True

    @pytest.mark.parametrize("name", [
        "recording.mp3", "interview.wav", "podcast.m4a", "audio.flac",
        "show.ogg", "clip.aac", "track.wma", "video.mp4", "book.m4b",
        "stream.opus", "media.webm",
    ])
    def test_returns_true_for_known_audio_extensions(self, name):
        assert gds.is_audio_file({"name": name, "mimeType": "application/octet-stream"}) is True

    @pytest.mark.parametrize("file_info", [
        {"name": "document.pdf", "mimeType": "application/pdf"},
        {"name": "image.jpg", "mimeType": "image/jpeg"},
        {"name": "spreadsheet.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        {"name": "video.avi", "mimeType": "video/x-msvideo"},  # video, not audio
    ])
    def test_returns_false_for_non_audio_files(self, file_info):
        assert gds.is_audio_file(file_info) is False

    def test_returns_false_for_empty_info(self):
        assert gds.is_audio_file({}) is False

    def test_mime_type_check_is_case_insensitive(self):
        assert gds.is_audio_file({"name": "f.bin", "mimeType": "Audio/MPEG"}) is True

    def test_extension_check_is_case_insensitive(self):
        assert gds.is_audio_file({"name": "RECORDING.MP3", "mimeType": ""}) is True


# ===========================================================================
# get_drive_service
# ===========================================================================
class TestGetDriveService:
    def test_builds_drive_v3_service(self):
        mock_creds = MagicMock()
        mock_service = MagicMock()
        with (
            patch("google.oauth2.service_account.Credentials.from_service_account_file",
                  return_value=mock_creds) as mock_cred_factory,
            patch("googleapiclient.discovery.build", return_value=mock_service) as mock_build,
        ):
            result = gds.get_drive_service()

        mock_cred_factory.assert_called_once()
        mock_build.assert_called_once_with("drive", "v3", credentials=mock_creds)
        assert result is mock_service


# ===========================================================================
# list_audio_files
# ===========================================================================
class TestListAudioFiles:
    def _make_service(self, files):
        mock_service = MagicMock()
        mock_service.files().list().execute.return_value = {"files": files}
        return mock_service

    def test_returns_only_audio_files(self):
        files = [
            {"id": "1", "name": "a.mp3", "mimeType": "audio/mpeg"},
            {"id": "2", "name": "b.pdf", "mimeType": "application/pdf"},
            {"id": "3", "name": "c.wav", "mimeType": "audio/wav"},
        ]
        mock_svc = self._make_service(files)
        with patch.object(gds, "get_drive_service", return_value=mock_svc):
            result = gds.list_audio_files()

        ids = [f["id"] for f in result]
        assert "1" in ids
        assert "3" in ids
        assert "2" not in ids

    def test_returns_empty_list_when_no_files(self):
        with patch.object(gds, "get_drive_service", return_value=self._make_service([])):
            assert gds.list_audio_files() == []

    def test_returns_empty_list_on_api_error(self):
        mock_svc = MagicMock()
        mock_svc.files().list().execute.side_effect = Exception("API error")
        with patch.object(gds, "get_drive_service", return_value=mock_svc):
            assert gds.list_audio_files() == []

    def test_returns_empty_list_when_folder_has_no_audio(self):
        files = [
            {"id": "x", "name": "report.docx", "mimeType": "application/msword"},
        ]
        with patch.object(gds, "get_drive_service", return_value=self._make_service(files)):
            assert gds.list_audio_files() == []


# ===========================================================================
# download_file
# ===========================================================================
class TestDownloadFile:
    def _make_downloader_sequence(self, chunks=3):
        """Simulate a MediaIoBaseDownload returning progress then done=True."""
        statuses = [MagicMock(progress=lambda: i / chunks) for i in range(1, chunks + 1)]
        done_values = [False] * (chunks - 1) + [True]
        return list(zip(statuses, done_values))

    def test_returns_local_path_on_success(self, tmp_path):
        mock_svc = MagicMock()
        downloader = MagicMock()
        downloader.next_chunk.side_effect = [(MagicMock(progress=lambda: 1.0), True)]

        with (
            patch.object(gds, "get_drive_service", return_value=mock_svc),
            patch("os.makedirs"),
            patch("os.path.abspath", return_value=str(tmp_path / "audio.mp3")),
            patch("io.FileIO"),
            patch("googleapiclient.http.MediaIoBaseDownload", return_value=downloader),
            patch.object(gds.config, "TEMP_DOWNLOAD_DIR", str(tmp_path)),
        ):
            result = gds.download_file("file-id", "audio.mp3")

        assert result == str(tmp_path / "audio.mp3")

    def test_returns_none_on_api_error(self):
        mock_svc = MagicMock()
        mock_svc.files().get_media.side_effect = Exception("Network error")

        with (
            patch.object(gds, "get_drive_service", return_value=mock_svc),
            patch("os.makedirs"),
            patch("os.path.abspath", return_value="/tmp/audio.mp3"),
        ):
            result = gds.download_file("bad-id", "audio.mp3")

        assert result is None

    def test_cleans_up_partial_download_on_error(self, tmp_path):
        partial_file = tmp_path / "partial.mp3"
        partial_file.write_bytes(b"partial")

        mock_svc = MagicMock()
        mock_svc.files().get_media.side_effect = Exception("Interrupted")

        with (
            patch.object(gds, "get_drive_service", return_value=mock_svc),
            patch("os.makedirs"),
            patch("os.path.abspath", return_value=str(partial_file)),
            patch("os.path.exists", return_value=True),
            patch("os.remove") as mock_remove,
        ):
            result = gds.download_file("bad-id", "partial.mp3")

        assert result is None
        mock_remove.assert_called_once_with(str(partial_file))
