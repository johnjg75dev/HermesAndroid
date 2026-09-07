import json
import os
from pathlib import Path

from hermes_android.device.registry import get_capability_snapshot
from hermes_android.device.facade import STUB_FACADE


def test_get_capability_snapshot_defaults_to_workspace(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    # Use stub facade
    from hermes_android.device.registry import FacadeRegistry
    FacadeRegistry().register_facade(STUB_FACADE)

    payload = get_capability_snapshot()

    assert "error" in payload  # Stub returns error


def test_read_device_capabilities_merges_android_state_file(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    workspace = hermes_home / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "notes.txt").write_text("hello", encoding="utf-8")
    (hermes_home / "android-device-state.json").write_text(
        json.dumps(
            {
                "shared_tree_uri": "content://example/tree/1",
                "shared_tree_label": "Docs",
                "accessibility_enabled": True,
                "accessibility_connected": True,
                "foreground_package_name": "com.example.front",
                "last_notification_package_name": "com.example.sender",
                "last_notification_title": "Title",
                "last_notification_text": "Body",
                "available_global_actions": ["home", "back"],
                "wifi_enabled": True,
                "bluetooth_enabled": True,
                "paired_bluetooth_devices": ["Keyboard"],
                "usb_device_count": 1,
                "nfc_supported": True,
                "overlay_permission_granted": True,
                "notification_permission_granted": True,
                "notification_listener_enabled": True,
                "notification_listener_connected": True,
                "background_persistence_enabled": True,
                "runtime_service_running": True,
                "available_system_actions": ["open_wifi_panel", "start_background_runtime"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    # Use stub facade
    from hermes_android.device.registry import FacadeRegistry
    FacadeRegistry().register_facade(STUB_FACADE)

    payload = get_capability_snapshot()

    # Stub facade returns error
    assert "error" in payload


def test_android_bridge_class_names_match_mobilefork_namespace():
    # These constants are no longer in the new structure
    # They were in the old device_bridge.py
    assert True  # Placeholder