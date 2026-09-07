import json

from hermes_android.linux.base import ExecutionMode, HealthStatus
from hermes_android.linux.env import apply_linux_subsystem_env, load_linux_subsystem_state
from hermes_android.linux.state import LinuxStateManager, LinuxSubsystemState


def _sample_info(shell_path="", native_library_dir="") -> LinuxSubsystemState:
    return LinuxSubsystemState(
        execution_mode=ExecutionMode.EMBEDDED.value,
        enabled=True,
        shell_path=shell_path,
        bash_path=shell_path,
        prefix_path="/data/local/hermes-linux/prefix",
        bin_path="/data/local/hermes-linux/prefix/bin",
        home_path="/data/local/hermes-linux/prefix/home",
        tmp_path="/data/local/hermes-linux/prefix/tmp",
        native_library_dir=native_library_dir,
        lib_path="/data/local/hermes-linux/prefix/lib",
        version_string="test",
    )


def test_load_linux_subsystem_state_returns_none_when_missing(tmp_path):
    manager = LinuxStateManager(tmp_path / "files")
    assert manager.load() is None


def test_apply_linux_subsystem_env_sets_terminal_backend_markers(tmp_path):
    files_dir = tmp_path / "files"
    state = _sample_info()
    LinuxStateManager(files_dir).save(state)

    env = apply_linux_subsystem_env(files_dir)

    assert env["TERMINAL_ENV"] == "android_linux"
    assert env["HERMES_ANDROID_EXECUTION_MODE"] == "embedded"
    assert env["HERMES_ANDROID_LINUX_PREFIX"] == "/data/local/hermes-linux/prefix"
    assert env["HOME"] == "/data/local/hermes-linux/prefix/home"
    assert env["TMPDIR"] == "/data/local/hermes-linux/prefix/tmp"


def test_apply_linux_subsystem_env_derives_native_lib_dir_from_shell_path(tmp_path):
    files_dir = tmp_path / "files"
    native_dir = files_dir / "hermes-home" / "linux" / "apk-lib"
    shell_path = native_dir / "libhermes_android_bash.so"
    native_dir.mkdir(parents=True)
    shell_path.write_text("", encoding="utf-8")

    state = _sample_info(shell_path=str(shell_path), native_library_dir="")
    LinuxStateManager(files_dir).save(state)

    env = apply_linux_subsystem_env(files_dir)

    assert env["HERMES_ANDROID_NATIVE_LIB"] == str(native_dir)
    assert str(native_dir) in env["LD_LIBRARY_PATH"]


def test_apply_linux_subsystem_env_is_noop_when_disabled(tmp_path):
    files_dir = tmp_path / "files"
    state = _sample_info()
    state.enabled = False
    LinuxStateManager(files_dir).save(state)

    assert apply_linux_subsystem_env(files_dir) == {}


def test_load_linux_subsystem_state_reads_raw_json(tmp_path):
    files_dir = tmp_path / "files"
    LinuxStateManager(files_dir).save(_sample_info())

    raw = load_linux_subsystem_state(files_dir)
    assert raw is not None
    assert raw["enabled"] is True
    assert json.loads(json.dumps(raw)) == raw


def test_state_roundtrip_preserves_health_and_mode(tmp_path):
    files_dir = tmp_path / "files"
    manager = LinuxStateManager(files_dir)
    state = _sample_info()
    state.health = HealthStatus.HEALTHY.value
    state.execution_mode = ExecutionMode.PROOT_DISTRO.value
    manager.save(state)

    loaded = manager.load()
    assert loaded is not None
    assert loaded.health == HealthStatus.HEALTHY.value
    assert loaded.execution_mode == ExecutionMode.PROOT_DISTRO.value
