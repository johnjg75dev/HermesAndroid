"""Tests for hermes-android package."""

import pytest


def test_version():
    """Test that version is accessible."""
    import hermes_android
    assert hasattr(hermes_android, "__version__")
    assert hermes_android.__version__ == "0.1.0"


def test_error_codes():
    """Test error code registry."""
    from hermes_android.errors import all_error_codes, get_error_code

    codes = all_error_codes()
    assert len(codes) > 0

    # Test lookup
    code = get_error_code("PROFILE_NOT_FOUND")
    assert code.code == "PROFILE_NOT_FOUND"

    # Test unknown code
    unknown = get_error_code("UNKNOWN_CODE_XYZ")
    assert unknown.code == "UNKNOWN_ERROR"


def test_bootstrap_phases():
    """Test boot phase enum."""
    from hermes_android.runtime.bootstrap import BootPhase

    phases = list(BootPhase)
    assert len(phases) == 9
    assert phases[0] == BootPhase.PROFILE
    assert phases[-1] == BootPhase.READY


def test_linux_execution_modes():
    """Test Linux execution modes."""
    from hermes_android.linux.base import ExecutionMode

    assert ExecutionMode.EMBEDDED.value == "embedded"
    assert ExecutionMode.PROOT_DISTRO.value == "proot"
    assert ExecutionMode.TERMUX.value == "termux"


def test_device_facade():
    """Test device facade protocol."""
    from hermes_android.device.facade import DeviceFacade, FacadeResult, STUB_FACADE

    # Test stub facade
    result = STUB_FACADE.terminal_exec("echo test")
    assert result.success is False
    assert result.error_code == "DEVICE_UNAVAILABLE"

    # Test FacadeResult helpers
    ok = FacadeResult.ok({"data": "test"})
    assert ok.success is True
    assert ok.data == {"data": "test"}

    err = FacadeResult.err("TEST_CODE", "Test message")
    assert err.success is False
    assert err.error_code == "TEST_CODE"


def test_profile_manager():
    """Test profile manager."""
    from hermes_android.profile.manager import ProfileManager

    mgr = ProfileManager()
    profiles = mgr.list_profiles()
    assert isinstance(profiles, list)


def test_bridge_versioning():
    """Test bridge versioning."""
    from hermes_android.api.versioning import (
        BRIDGE_VERSION,
        MIN_BRIDGE_VERSION,
        get_bridge_version_info,
        check_bridge_version,
    )

    assert BRIDGE_VERSION >= MIN_BRIDGE_VERSION

    info = get_bridge_version_info()
    assert info.version == BRIDGE_VERSION

    # Test compatible version
    ok, err = check_bridge_version(BRIDGE_VERSION)
    assert ok is True
    assert err is None

    # Test too old
    ok, err = check_bridge_version(MIN_BRIDGE_VERSION - 1)
    assert ok is False
    assert "UNSUPPORTED_BRIDGE_VERSION" in err

    # Test too new
    ok, err = check_bridge_version(BRIDGE_VERSION + 1)
    assert ok is False
    assert "UNSUPPORTED_BRIDGE_VERSION" in err


if __name__ == "__main__":
    pytest.main([__file__, "-v"])