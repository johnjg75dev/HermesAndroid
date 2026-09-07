"""Tests for the Kotlin -> Python on-device provider catalog plumbing."""

import json

import pytest

from hermes_android.providers.android_local import (
    catalog_path,
    load_catalog_from_disk,
    register_android_local_providers,
    registered_backends,
    sync_android_local_catalog,
    unregister_android_local_provider,
)


@pytest.fixture
def files_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_ANDROID_FILES_DIR", str(tmp_path))
    return tmp_path


def _write_catalog(files_dir, models):
    (files_dir / "local-model-catalog.json").write_text(
        json.dumps({"models": models}), encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def _clean_registry():
    yield
    for backend in registered_backends():
        unregister_android_local_provider(backend["model_id"])


def test_catalog_path_uses_files_dir_env(files_dir):
    assert catalog_path() == files_dir / "local-model-catalog.json"


def test_load_catalog_tolerates_missing_or_corrupt_file(files_dir):
    assert load_catalog_from_disk() == {}
    (files_dir / "local-model-catalog.json").write_text("{not json", encoding="utf-8")
    assert load_catalog_from_disk() == {}


def test_sync_registers_verified_models_and_exposes_backends(files_dir, monkeypatch):
    # providers._REGISTRY is process-global; isolate it per test.
    from providers import _REGISTRY

    monkeypatch.setattr(
        "providers._REGISTRY", {k: v for k, v in _REGISTRY.items() if not k.startswith("android_local_")},
    )
    _write_catalog(files_dir, {
        "gemma-4-e2b": {
            "verified": True,
            "backend": "litertlm",
            "loopback_port": 15436,
            "display_name": "Gemma 4 E2B",
        },
        "unverified-model": {"verified": False, "backend": "litertlm", "loopback_port": 1},
    })

    ids = sync_android_local_catalog()

    assert ids == ["gemma-4-e2b"]
    backends = registered_backends()
    assert len(backends) == 1
    assert backends[0]["model_id"] == "gemma-4-e2b"
    assert backends[0]["loopback_port"] == 15436
    assert backends[0]["profile_name"] == "android_local_gemma-4-e2b"


def test_sync_unregisters_models_that_left_the_catalog(files_dir):
    _write_catalog(files_dir, {
        "temp-model": {
            "verified": True,
            "backend": "llama_cpp",
            "loopback_port": 15435,
            "display_name": "Temp",
        },
    })
    assert sync_android_local_catalog() == ["temp-model"]

    # Model stopped: Kotlin rewrites the file with an empty catalog.
    _write_catalog(files_dir, {})
    assert sync_android_local_catalog() == []
    assert registered_backends() == []
