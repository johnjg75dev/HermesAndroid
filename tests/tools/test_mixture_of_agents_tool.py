import importlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

moa = importlib.import_module("tools.mixture_of_agents_tool")


def test_moa_defaults_are_well_formed():
    # Invariants, not a catalog snapshot: the exact model list churns with
    # OpenRouter availability (see PR #6636 where gemini-3-pro-preview was
    # removed upstream). What we care about is that the defaults are present
    # and valid vendor/model slugs.
    assert isinstance(moa.REFERENCE_MODELS, list)
    assert len(moa.REFERENCE_MODELS) >= 1
    for m in moa.REFERENCE_MODELS:
        assert isinstance(m, str) and "/" in m and not m.startswith("/")
    assert isinstance(moa.AGGREGATOR_MODEL, str)
    assert "/" in moa.AGGREGATOR_MODEL


@pytest.mark.asyncio
async def test_reference_model_retry_warnings_avoid_exc_info_until_terminal_failure(monkeypatch):
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=AsyncMock(side_effect=RuntimeError("rate limited"))
            )
        )
    )
    warn = MagicMock()
    err = MagicMock()

    monkeypatch.setattr(moa, "_get_openrouter_client", lambda: fake_client)
    monkeypatch.setattr(moa.logger, "warning", warn)
    monkeypatch.setattr(moa.logger, "error", err)

    model, message, success = await moa._run_reference_model_safe(
        "openai/gpt-5.4-pro", "hello", max_retries=2
    )

    assert model == "openai/gpt-5.4-pro"
    assert success is False
    assert "failed after 2 attempts" in message
    assert warn.call_count == 2
    assert all(call.kwargs.get("exc_info") is None for call in warn.call_args_list)
    err.assert_called_once()
    assert err.call_args.kwargs.get("exc_info") is True


@pytest.mark.asyncio
async def test_moa_top_level_error_logs_single_traceback_on_aggregator_failure(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(
        moa,
        "_run_reference_model_safe",
        AsyncMock(return_value=("anthropic/claude-opus-4.6", "ok", True)),
    )
    monkeypatch.setattr(
        moa,
        "_run_aggregator_model",
        AsyncMock(side_effect=RuntimeError("aggregator boom")),
    )
    monkeypatch.setattr(
        moa,
        "_debug",
        SimpleNamespace(log_call=MagicMock(), save=MagicMock(), active=False),
    )

    err = MagicMock()
    monkeypatch.setattr(moa.logger, "error", err)

    result = json.loads(
        await moa.mixture_of_agents_tool(
            "solve this",
            reference_models=["anthropic/claude-opus-4.6"],
        )
    )

    assert result["success"] is False
    assert "Error in MoA processing" in result["error"]
    err.assert_called_once()
    assert err.call_args.kwargs.get("exc_info") is True


def test_config_roster_overrides_constants(monkeypatch):
    """P1 gate: config roster overrides tool constants."""
    fake_cfg = {
        "moa": {
            "reference_models": ["vendor/alpha", "vendor/beta"],
            "aggregator_model": "vendor/synth",
        }
    }
    monkeypatch.setattr(moa, "_load_moa_config", lambda: fake_cfg.get("moa", {}))

    models, aggregator = moa.resolved_moa_roster()

    assert models == ["vendor/alpha", "vendor/beta"]
    assert aggregator == "vendor/synth"

    config_view = moa.get_moa_configuration()
    assert config_view["reference_models"] == ["vendor/alpha", "vendor/beta"]
    assert config_view["aggregator_model"] == "vendor/synth"


def test_explicit_args_win_over_config(monkeypatch):
    monkeypatch.setattr(
        moa,
        "_load_moa_config",
        lambda: {"reference_models": ["vendor/config"], "aggregator_model": "vendor/cfg-agg"},
    )
    models, aggregator = moa.resolved_moa_roster(
        reference_models=["vendor/arg"], aggregator_model="vendor/arg-agg"
    )
    assert models == ["vendor/arg"]
    assert aggregator == "vendor/arg-agg"


def test_invalid_config_entries_fall_back_per_key(monkeypatch):
    monkeypatch.setattr(
        moa,
        "_load_moa_config",
        lambda: {"reference_models": "not-a-list", "aggregator_model": 42},
    )
    models, aggregator = moa.resolved_moa_roster()
    # Bad list falls back to constants; scalar coercion still applies.
    assert models == list(moa.REFERENCE_MODELS)
    assert aggregator == str(42)


def test_missing_config_section_uses_constants(monkeypatch):
    monkeypatch.setattr(moa, "_load_moa_config", lambda: {})
    models, aggregator = moa.resolved_moa_roster()
    assert models == list(moa.REFERENCE_MODELS)
    assert aggregator == moa.AGGREGATOR_MODEL
