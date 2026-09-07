from pathlib import Path
import sys

# Add src directory for new hermes-android package structure
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "hermes_android" / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from hermes_android.config.defaults import (
    DEFAULT_ANDROID_API_SERVER_TOOLSETS,
    ensure_android_defaults,
    resolved_android_api_server_toolsets,
    should_force_android_api_server_toolsets,
)


def test_resolved_android_api_server_toolsets_defaults_for_missing_config():
    assert resolved_android_api_server_toolsets({}) == DEFAULT_ANDROID_API_SERVER_TOOLSETS
    assert should_force_android_api_server_toolsets({}) is True


def test_resolved_android_api_server_toolsets_defaults_for_invalid_override():
    config = {"platform_toolsets": {"api_server": ["does-not-exist"]}}
    assert resolved_android_api_server_toolsets(config) == DEFAULT_ANDROID_API_SERVER_TOOLSETS
    assert should_force_android_api_server_toolsets(config) is True


def test_resolved_android_api_server_toolsets_respects_valid_override():
    config = {"platform_toolsets": {"api_server": ["web", "terminal"]}}
    assert resolved_android_api_server_toolsets(config) == ["web", "terminal"]
    assert should_force_android_api_server_toolsets(config) is False


def test_ensure_android_defaults_persists_api_server_toolset(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    config = ensure_android_defaults(config={}, persist=True)

    assert config["platform_toolsets"]["api_server"] == DEFAULT_ANDROID_API_SERVER_TOOLSETS
    config_text = (hermes_home / "config.yaml").read_text()
    assert "platform_toolsets:" in config_text
    assert "hermes-android-app" in config_text
