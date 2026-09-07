import os
import sys

# Add src directory for new hermes-android package structure
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "hermes_android" / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from hermes_android.runtime.env import hermes_home_for, prepare_runtime_env


def test_prepare_runtime_env_sets_android_env_and_dirs(tmp_path, monkeypatch):
    monkeypatch.delenv("HERMES_HOME", raising=False)
    files_dir = tmp_path / "files"
    runtime = prepare_runtime_env(
        files_dir,
        api_server_port=8765,
        api_server_key="secret-key",
    )

    assert runtime.files_dir == files_dir.resolve()
    assert runtime.hermes_home == files_dir.resolve() / "hermes-home"
    # Default bind is all interfaces so LAN clients can reach the agent API;
    # status URLs still advertise loopback separately for on-device clients.
    assert runtime.api_server_host == "0.0.0.0"
    assert runtime.api_server_port == 8765
    assert runtime.api_server_key == "secret-key"

    for child in ("logs", "sessions", "skills", "downloads", "workspace"):
        assert (runtime.hermes_home / child).is_dir()

    assert os.environ["HERMES_HOME"] == str(runtime.hermes_home)
    assert os.environ["HERMES_ANDROID_BOOTSTRAP"] == "1"
    assert os.environ["API_SERVER_HOST"] == "0.0.0.0"
    assert os.environ["API_SERVER_PORT"] == "8765"
    assert os.environ["API_SERVER_KEY"] == "secret-key"
    assert os.environ["API_SERVER_MODEL_NAME"] == "hermes-agent-android"


def test_prepare_runtime_env_generates_port_and_key(tmp_path, monkeypatch):
    monkeypatch.delenv("HERMES_HOME", raising=False)
    runtime = prepare_runtime_env(tmp_path / "files")

    assert runtime.api_server_port > 0
    assert runtime.api_server_key


def test_prepare_runtime_env_honors_preset_hermes_home(tmp_path, monkeypatch):
    """Boot phase 1 (profile manager) owns HERMES_HOME; later phases respect it."""
    pinned_home = tmp_path / "profiles" / "work" / "hermes-home"
    pinned_home.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(pinned_home))

    runtime = prepare_runtime_env(tmp_path / "files")

    assert runtime.hermes_home == pinned_home.resolve()
    assert os.environ["HERMES_HOME"] == str(pinned_home.resolve())


def test_hermes_home_for_defaults_without_preset(tmp_path, monkeypatch):
    monkeypatch.delenv("HERMES_HOME", raising=False)
    assert hermes_home_for(tmp_path / "files") == (tmp_path / "files" / "hermes-home").resolve()
