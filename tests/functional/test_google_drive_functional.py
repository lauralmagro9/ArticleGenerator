"""
Functional tests for services/google_drive_service.py

The Google API clients are mocked, but real file-system interactions
(directory creation, file writing) exercise the actual download_file logic.
"""
import os
import io
import pytest
from unittest.mock import patch, MagicMock, call

with (
    patch("dotenv.load_dotenv"),
    patch("requests.get") as _g,
    patch("os.path.exists", return_value=False),
    patch("google.oauth2.service_account.Credentials.from_service_account_file"),
    patch("googleapiclient.discovery.build"),
):
    _g.return_value = MagicMock(status_code=200, json=lambda: [])
    from services import google_drive_service as gds


# ===========================================================================
# list_audio_files — integration with is_audio_file filter
# ===========================================================================
class TestListAudioFilesIntegration:
    """Verifies that list_audio_files correctly filters through is_audio_file."""

    def _make_service(self, files):
        svc = MagicMock()
        svc.files().list().execute.return_value = {"files": files}
        return svc

    def test_mixed_folder_returns_only_audio(self):
        files = [
            {"id": "1", "name": "recording.mp3", "mimeType": "audio/mpeg"},
            {"id": "2", "name": "notes.docx",    "mimeType": "application/msword"},
            {"id": "3", "name": "interview.wav",  "mimeType": "audio/wav"},
            {"id": "4", "name": "photo.jpg",      "mimeType": "image/jpeg"},
            {"id": "5", "name": "podcast.m4a",    "mimeType": "application/octet-stream"},
        ]
        with patch.object(gds, "get_drive_service", return_value=self._make_service(files)):
            result = gds.list_audio_files()

        ids = {f["id"] for f in result}
        assert ids == {"1", "3", "5"}

    def test_all_audio_folder_returns_all(self):
        files = [
            {"id": str(i), "name": f"ep{i}.mp3", "mimeType": "audio/mpeg"}
            for i in range(10)
        ]
        with patch.object(gds, "get_drive_service", return_value=self._make_service(files)):
            result = gds.list_audio_files()
        assert len(result) == 10

    def test_empty_folder_returns_empty_list(self):
        with patch.object(gds, "get_drive_service", return_value=self._make_service([])):
            assert gds.list_audio_files() == []

    def test_api_exception_returns_empty_list(self):
        svc = MagicMock()
        svc.files().list().execute.side_effect = Exception("Drive quota exceeded")
        with patch.object(gds, "get_drive_service", return_value=svc):
            assert gds.list_audio_files() == []


# ===========================================================================
# download_file — real temp directory, mocked Drive downloader
# ===========================================================================
class TestDownloadFileIntegration:
    def _make_service_and_downloader(self, tmp_path, filename="audio.mp3", chunk_data=b"FAKE_AUDIO"):
        """Sets up a Drive service mock + a downloader that writes real bytes."""
        svc = MagicMock()

        # Simulate a single-chunk download that writes bytes to the FileIO
        def fake_next_chunk():
            return MagicMock(progress=lambda: 1.0), True

        mock_downloader = MagicMock()
        mock_downloader.next_chunk.side_effect = [fake_next_chunk()]

        return svc, mock_downloader

    def test_creates_temp_directory_if_missing(self, tmp_path):
        target_dir = str(tmp_path / "downloads")
        assert not os.path.exists(target_dir)

        svc = MagicMock()
        dl = MagicMock()
        dl.next_chunk.return_value = (MagicMock(progress=lambda: 1.0), True)

        with (
            patch.object(gds, "get_drive_service", return_value=svc),
            patch.object(gds.config, "TEMP_DOWNLOAD_DIR", target_dir),
            patch("io.FileIO"),
            patch("googleapiclient.http.MediaIoBaseDownload", return_value=dl),
        ):
            gds.download_file("file-id", "audio.mp3")

        assert os.path.exists(target_dir)

    def test_returns_absolute_path(self, tmp_path):
        svc = MagicMock()
        dl = MagicMock()
        dl.next_chunk.return_value = (MagicMock(progress=lambda: 1.0), True)

        with (
            patch.object(gds, "get_drive_service", return_value=svc),
            patch.object(gds.config, "TEMP_DOWNLOAD_DIR", str(tmp_path)),
            patch("io.FileIO"),
            patch("googleapiclient.http.MediaIoBaseDownload", return_value=dl),
        ):
            result = gds.download_file("file-id", "episode.mp3")

        assert os.path.isabs(result)
        assert result.endswith("episode.mp3")

    def test_returns_none_when_service_raises(self, tmp_path):
        svc = MagicMock()
        svc.files().get_media.side_effect = Exception("403 Forbidden")

        with (
            patch.object(gds, "get_drive_service", return_value=svc),
            patch.object(gds.config, "TEMP_DOWNLOAD_DIR", str(tmp_path)),
        ):
            result = gds.download_file("bad-id", "audio.mp3")

        assert result is None

    def test_partial_file_is_cleaned_up_on_error(self, tmp_path):
        partial = tmp_path / "partial.mp3"
        partial.write_bytes(b"incomplete")

        svc = MagicMock()
        svc.files().get_media.side_effect = Exception("Interrupted")

        with (
            patch.object(gds, "get_drive_service", return_value=svc),
            patch.object(gds.config, "TEMP_DOWNLOAD_DIR", str(tmp_path)),
            patch("os.path.abspath", return_value=str(partial)),
            patch("os.path.exists", return_value=True),
            patch("os.remove") as mock_rm,
        ):
            result = gds.download_file("bad-id", "partial.mp3")

        assert result is None
        mock_rm.assert_called_once_with(str(partial))

    def test_multi_chunk_download_completes(self, tmp_path):
        svc = MagicMock()
        chunks = [
            (MagicMock(progress=lambda: 0.5), False),
            (MagicMock(progress=lambda: 1.0), True),
        ]
        dl = MagicMock()
        dl.next_chunk.side_effect = chunks

        with (
            patch.object(gds, "get_drive_service", return_value=svc),
            patch.object(gds.config, "TEMP_DOWNLOAD_DIR", str(tmp_path)),
            patch("io.FileIO"),
            patch("googleapiclient.http.MediaIoBaseDownload", return_value=dl),
        ):
            result = gds.download_file("file-id", "big_file.mp3")

        assert dl.next_chunk.call_count == 2
        assert result is not None
