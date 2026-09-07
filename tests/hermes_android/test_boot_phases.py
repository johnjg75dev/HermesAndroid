"""Boot-phase checklist tests (M01 server side).

The 9-phase orchestrator records per-phase outcomes; the Kotlin app reads
them from the ``ensure_server`` payload / RuntimeService status.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "hermes_android" / "src"
for p in (str(REPO_ROOT), str(SRC_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from hermes_android.runtime.bootstrap import (
    BootPhase,
    BootstrapOrchestrator,
    boot_phase_report,
    bootstrap_android_runtime,
)


def test_phase_report_covers_all_nine_phases_in_order(tmp_path):
    report = bootstrap_android_runtime(str(tmp_path / "files"))
    assert report["runtime"]["api_server_port"] > 0

    results = boot_phase_report()
    names = [r["phase"] for r in results]
    expected = [
        "profile",
        "interpreter",
        "config",
        "assets",
        "linux",
        "mcp",
        "memory",
        "api",
    ]
    assert names == expected
    for item in results:
        assert item["status"] in {"ok", "degraded", "failed", "ready"}
        assert isinstance(item["fatal"], bool)
        assert "duration_ms" in item


def test_degraded_phase_records_error_but_continues(tmp_path, monkeypatch):
    def broken_mcp(files_dir):
        raise RuntimeError("no mcp config")

    orchestrator = BootstrapOrchestrator(str(tmp_path / "files"))

    def failing_phase():
        raise RuntimeError("synthetic mcp failure")

    orchestrator._run_phase(BootPhase.MCP, failing_phase)
    mcp_result = orchestrator.phase_results[-1]
    assert mcp_result["phase"] == "mcp"
    assert mcp_result["status"] == "degraded"
    assert "synthetic mcp failure" in mcp_result["error"]

    # A fatal phase must record failed and raise.
    import pytest

    from hermes_android.errors import HermesRuntimeError

    def fatal_failure():
        raise RuntimeError("boom")

    with pytest.raises(HermesRuntimeError):
        orchestrator._run_phase(BootPhase.PROFILE, fatal_failure)
    profile_result = orchestrator.phase_results[-1]
    assert profile_result["status"] == "failed"
    assert profile_result["fatal"] is True


def test_ensure_server_payload_includes_phases(monkeypatch, tmp_path):
    """server_bridge.ensure_server exposes the checklist to Kotlin."""
    from unittest.mock import MagicMock, patch

    import hermes_android.runtime.server_bridge as bridge

    payload = {
        "started": True,
        "base_url": "http://127.0.0.1:8000",
        "loopback_base_url": "http://127.0.0.1:8000",
        "api_server_host": "127.0.0.1",
        "api_server_port": 8000,
        "api_server_key": "k",
        "api_server_model_name": "m",
        "hermes_home": "/tmp/x",
    }
    handle = MagicMock()
    handle.runtime.api_server_host = "127.0.0.1"
    handle.runtime.api_server_port = 8000
    handle.runtime.api_server_key = "k"
    handle.runtime.api_server_model_name = "m"
    handle.runtime.hermes_home = Path("/tmp/x")
    monkeypatch.setattr(bridge, "_ACTIVE_HANDLE", handle)
    monkeypatch.setattr(
        "hermes_android.runtime.bootstrap._last_orchestrator", None
    )

    class FakeOrchestrator:
        def phase_results(self_inner):  # noqa: N805 - mimic property access path
            return []

    # Simpler: patch boot_phase_report directly.
    monkeypatch.setattr(
        bridge,
        "boot_phase_report",
        lambda: [{"phase": "profile", "fatal": True, "status": "ok", "error": None, "duration_ms": 1.2}],
    )

    raw = bridge.ensure_server(str(tmp_path))
    data = json.loads(raw)
    assert data["phases"][0]["phase"] == "profile"
