"""P2 wiring tests: Kotlin facade bridge contract, health monitor, SSH probe."""

import json
import threading
import time

import pytest

from hermes_android.device.facade import FacadeResult, STUB_FACADE
from hermes_android.device.registry import get_facade


# ---------------------------------------------------------------------------
# KotlinDispatchFacade — bridge wire contract (mocked jclass)
# ---------------------------------------------------------------------------


class _FakeJClass:
    """Stands in for com.mobilefork...HermesDeviceFacadeBridge over Chaquopy."""

    responses: dict[str, str] = {}

    @classmethod
    def dispatchJson(cls, operation: str, payload_json: str) -> str:
        payload = json.loads(payload_json)
        assert payload["op"] == operation
        return cls.responses[operation]


@pytest.fixture
def fake_bridge(monkeypatch):
    monkeypatch.setattr(
        "hermes_android.device.kotlin_facade._bridge_class", lambda: _FakeJClass,
    )
    yield _FakeJClass


def test_facade_parses_success_envelope(fake_bridge):
    from hermes_android.device.kotlin_facade import KotlinDispatchFacade

    fake_bridge.responses = {
        "file_read": json.dumps({"success": True, "data": "hello world"}),
    }

    result = KotlinDispatchFacade().file_read("/tmp/x.txt")

    assert result.success
    assert result.data == "hello world"


def test_facade_maps_error_envelope_to_typed_code(fake_bridge):
    from hermes_android.device.kotlin_facade import KotlinDispatchFacade

    fake_bridge.responses = {
        "terminal_exec": json.dumps({
            "success": False,
            "error_code": "FACADE_TIMEOUT",
            "error_message": "timed out after 30s",
        }),
    }

    result = KotlinDispatchFacade().terminal_exec("sleep 999")

    assert not result.success
    assert result.error_code == "FACADE_TIMEOUT"
    assert "timed out" in result.error_message


def test_facade_transport_failure_is_typed_device_unavailable(fake_bridge):
    from hermes_android.device.kotlin_facade import KotlinDispatchFacade

    def boom(operation, payload_json):
        raise RuntimeError("chaquopy bridge gone")

    fake_bridge.dispatchJson = classmethod(lambda cls, op, pj: boom(op, pj))

    result = KotlinDispatchFacade().clipboard_get()

    assert not result.success
    assert result.error_code == "DEVICE_UNAVAILABLE"
    assert "bridge gone" in result.error_message


def test_try_register_noop_without_chaquopy(monkeypatch):
    import hermes_android.device.kotlin_facade as kf

    monkeypatch.setattr(kf, "kotlin_facade_available", lambda: False)
    assert kf.try_register_kotlin_facade() is False
    # Registry still holds the stub — agent calls degrade gracefully.
    assert get_facade() is STUB_FACADE


# ---------------------------------------------------------------------------
# Health monitor singleton — persists transitions to the state file
# ---------------------------------------------------------------------------


class _FlakySubsystem:
    """Subsystem double whose health flips between probes."""

    def __init__(self):
        self.calls = 0
        from hermes_android.linux.base import ExecutionMode, HealthStatus, SubsystemInfo

        self.ExecutionMode = ExecutionMode
        self.HealthStatus = HealthStatus
        self.SubsystemInfo = SubsystemInfo
        self.execution_mode = ExecutionMode.EMBEDDED

    def probe(self):
        self.calls += 1
        health = (
            self.HealthStatus.HEALTHY if self.calls == 1 else self.HealthStatus.DEGRADED
        )
        return self.SubsystemInfo(
            execution_mode=self.execution_mode,
            health=health,
            shell_path="/data/sh",
            bash_path="/data/bash",
            prefix_path="/data/prefix",
            bin_path="/data/bin",
            home_path="/data/home",
            tmp_path="/data/tmp",
            native_library_dir="/data/lib",
            lib_path="/data/lib",
            version="test",
        )


@pytest.fixture
def monitor_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_ANDROID_FILES_DIR", str(tmp_path))
    import hermes_android.linux.monitor as monitor

    monkeypatch.setattr(monitor, "_monitor", None)
    monkeypatch.setattr(monitor, "_last_status", "")
    yield tmp_path, monitor
    monitor.stop_health_monitor()


def test_health_monitor_persists_transitions_within_tick(monitor_env, monkeypatch):
    tmp_path, monitor = monitor_env
    flaky = _FlakySubsystem()

    # Pre-seed a Kotlin-owned state file with extra keys that must survive.
    state_dir = tmp_path / "hermes-home" / "linux"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "linux-subsystem-state.json").write_text(
        json.dumps({
            "runtime_layout_version": 7,
            "asset_manifest_sha256": "abc123",
            "native_bash_path": "/data/native/bash",
            "apk_packages": 3,
            "distro": "ubuntu-24.04",
        }),
        encoding="utf-8",
    )

    # Deterministic subsystem + fast interval instead of the real factory.
    monkeypatch.setattr(
        "hermes_android.linux.base.LinuxSubsystemFactory.create_subsystem",
        lambda self: flaky,
    )
    assert monitor.start_health_monitor(interval_seconds=0.05) is True
    assert monitor.health_monitor_running()

    # Wait for at least one flip healthy -> degraded.
    deadline = time.time() + 5
    while time.time() < deadline:
        state_file = tmp_path / "hermes-home" / "linux" / "linux-subsystem-state.json"
        if state_file.is_file():
            data = json.loads(state_file.read_text(encoding="utf-8"))
            if data.get("health") == "degraded":
                break
        time.sleep(0.05)

    data = json.loads(
        (tmp_path / "hermes-home" / "linux" / "linux-subsystem-state.json").read_text(
            encoding="utf-8",
        ),
    )
    assert data["health"] == "degraded"
    assert data["last_probe_epoch_ms"] > 0
    # Kotlin-owned keys survive health updates (merge, never replace).
    assert data["runtime_layout_version"] == 7
    assert data["asset_manifest_sha256"] == "abc123"
    assert data["native_bash_path"] == "/data/native/bash"
    assert data["apk_packages"] == 3
    assert data["distro"] == "ubuntu-24.04"


def test_start_health_monitor_is_idempotent(monitor_env, monkeypatch):
    _, monitor = monitor_env
    monkeypatch.setattr(
        "hermes_android.linux.base.LinuxSubsystemFactory.create_subsystem",
        lambda self: _FlakySubsystem(),
    )

    assert monitor.start_health_monitor(interval_seconds=30) is True
    first = monitor._monitor
    assert monitor.start_health_monitor(interval_seconds=30) is True
    assert monitor._monitor is first  # same instance, no duplicate threads
    monitor.stop_health_monitor()
    assert monitor.health_monitor_running() is False


# ---------------------------------------------------------------------------
# SSH backend probe (locked decision 3)
# ---------------------------------------------------------------------------


def test_ssh_probe_reports_none_when_wheels_absent(monkeypatch):
    import hermes_android.api.manage.linux as linux_routes

    monkeypatch.setattr(linux_routes, "_SSH_BACKEND_CACHE", None)
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name in ("asyncssh", "paramiko"):
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    try:
        assert linux_routes.probe_ssh_backend() == "none"
    finally:
        monkeypatch.setattr(linux_routes, "_SSH_BACKEND_CACHE", None)


def test_ssh_probe_prefers_asyncssh_and_caches(monkeypatch):
    import sys
    import types

    import hermes_android.api.manage.linux as linux_routes

    monkeypatch.setattr(linux_routes, "_SSH_BACKEND_CACHE", None)
    fake = types.ModuleType("asyncssh")
    monkeypatch.setitem(sys.modules, "asyncssh", fake)
    try:
        assert linux_routes.probe_ssh_backend() == "asyncssh"
        # Cached: removing the module must not change the answer.
        monkeypatch.setitem(sys.modules, "asyncssh", None)
        assert linux_routes.probe_ssh_backend() == "asyncssh"
    finally:
        monkeypatch.setattr(linux_routes, "_SSH_BACKEND_CACHE", None)


def test_linux_status_includes_ssh_backend(monkeypatch):
    from aiohttp.test_utils import make_mocked_request
    import hermes_android.api.manage.linux as linux_routes

    monkeypatch.delenv("HERMES_ANDROID_FILES_DIR", raising=False)
    monkeypatch.setattr(linux_routes, "_SSH_BACKEND_CACHE", "none")
    request = make_mocked_request("GET", "/v1/manage/linux")
    response = linux_routes._collect()  # direct call; route handler wraps it
    assert response["ssh_backend"] == "none"
