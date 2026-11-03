"""
Unit tests for config.validate_config()

The module-level side-effects (dotenv, requests, tomllib) are patched via
importlib so each test case controls the env vars independently.
"""
import importlib
import sys
import types
import pytest
from unittest.mock import patch, MagicMock


def _fresh_config(env_overrides: dict, credentials_exist: bool = True):
    """
    Reloads the config module with a controlled environment.
    Returns the reloaded module object.
    """
    # Remove cached module so we get a clean import
    for key in list(sys.modules.keys()):
        if key == "config" or key.startswith("config."):
            del sys.modules[key]

    base_env = {
        "GOOGLE_DRIVE_FOLDER_ID": "folder-123",
        "GEMINI_API_KEY": "gemini-key",
        "WORDPRESS_URL": "https://myblog.com",
        "WORDPRESS_USER": "admin",
        "WORDPRESS_APP_PASSWORD": "secret",
        "GOOGLE_CLIENT_SECRET": "credentials.json",
    }
    base_env.update(env_overrides)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = []

    with (
        patch("os.getenv", side_effect=lambda k, *d: base_env.get(k, d[0] if d else None)),
        patch("os.path.exists", return_value=credentials_exist),
        patch("dotenv.load_dotenv"),
        patch("requests.get", return_value=mock_response),
        # Suppress settings.toml loading
        patch("tomllib.load", return_value={}),
    ):
        config = importlib.import_module("config")

    return config


# ===========================================================================
# validate_config
# ===========================================================================
class TestValidateConfig:
    def _make_config(self, env_overrides=None, credentials_exist=True):
        return _fresh_config(env_overrides or {}, credentials_exist)

    def test_returns_true_when_all_config_present(self):
        cfg = self._make_config()
        with patch("os.path.exists", return_value=True):
            assert cfg.validate_config() is True

    @pytest.mark.parametrize("missing_key", [
        "GOOGLE_DRIVE_FOLDER_ID",
        "GEMINI_API_KEY",
        "WORDPRESS_URL",
        "WORDPRESS_USER",
        "WORDPRESS_APP_PASSWORD",
    ])
    def test_returns_false_when_required_key_missing(self, missing_key):
        cfg = self._make_config(env_overrides={missing_key: None})
        with patch("os.path.exists", return_value=True):
            result = cfg.validate_config()
        assert result is False

    def test_returns_false_when_credentials_file_missing(self):
        cfg = self._make_config(credentials_exist=False)
        # Even with all env vars set, missing credentials file → False
        with patch("os.path.exists", return_value=False):
            result = cfg.validate_config()
        assert result is False

    def test_returns_true_when_credentials_file_present(self):
        cfg = self._make_config()
        with patch("os.path.exists", return_value=True):
            assert cfg.validate_config() is True

    def test_returns_false_when_multiple_keys_missing(self):
        cfg = self._make_config(env_overrides={
            "GEMINI_API_KEY": None,
            "WORDPRESS_USER": None,
        })
        with patch("os.path.exists", return_value=True):
            assert cfg.validate_config() is False
