#!/usr/bin/env python3
"""
Mixture-of-Agents Tool Module

This module implements the Mixture-of-Agents (MoA) methodology that leverages
the collective strengths of multiple LLMs through a layered architecture to
achieve state-of-the-art performance on complex reasoning tasks.

Based on the research paper: "Mixture-of-Agents Enhances Large Language Model Capabilities"
by Junlin Wang et al. (arXiv:2406.04692v1)

Key Features:
- Multi-layer LLM collaboration for enhanced reasoning
- Parallel processing of reference models for efficiency
- Intelligent aggregation and synthesis of diverse responses
- Specialized for extremely difficult problems requiring intense reasoning
- Optimized for coding, mathematics, and complex analytical tasks

Available Tool:
- mixture_of_agents_tool: Process complex queries using multiple frontier models

Architecture:
1. Reference models generate diverse initial responses in parallel
2. Aggregator model synthesizes responses into a high-quality output
3. Multiple layers can be used for iterative refinement (future enhancement)

Models Used (via OpenRouter):
- Reference Models: claude-opus-4.6, gemini-3-pro-preview, gpt-5.4-pro, deepseek-v3.2
- Aggregator Model: claude-opus-4.6 (highest capability for synthesis)

Configuration:
    To customize the MoA setup, modify the configuration constants at the top of this file:
    - REFERENCE_MODELS: List of models for generating diverse initial responses
    - AGGREGATOR_MODEL: Model used to synthesize the final response
    - REFERENCE_TEMPERATURE/AGGREGATOR_TEMPERATURE: Sampling temperatures
    - MIN_SUCCESSFUL_REFERENCES: Minimum successful models needed to proceed

Usage:
    from mixture_of_agents_tool import mixture_of_agents_tool
    import asyncio
    
    # Process a complex query
    result = await mixture_of_agents_tool(
        user_prompt="Solve this complex mathematical proof..."
    )
"""

import json
import logging
import os
import asyncio
import datetime
import threading
from typing import Dict, Any, List, Optional, Callable
from tools.openrouter_client import get_async_client as _get_openrouter_client, check_api_key as check_openrouter_api_key
from agent.auxiliary_client import extract_content_or_reasoning
from tools.debug_helpers import DebugSession
import sys

logger = logging.getLogger(__name__)


# =========================================================================
# MoA progress hook (gateway → client bridge)
# =========================================================================
# Mirrors tools.approval's gateway-notify registry: long-running clients
# (Android app, api_server SSE) register a per-session listener and receive
# structured member progress while a MoA run executes.  The session key is
# read from the same contextvar the approval system uses, so events are
# attributed to the correct concurrent run without extra plumbing.
#
# Events emitted:
#   moa.member.start     {model}
#   moa.member.done      {model, success, duration}
#   moa.aggregate.start  {model}
#   moa.done             {success}

_moa_notify_lock = threading.Lock()
_moa_notify_cbs: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}


def register_moa_notify(session_key: str, cb: Callable[[Dict[str, Any]], None]) -> None:
    """Register a per-session listener for MoA member/aggregate progress."""
    with _moa_notify_lock:
        _moa_notify_cbs.setdefault(session_key, []).append(cb)


def unregister_moa_notify(session_key: str, cb: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
    """Drop listeners for a session (all of them when ``cb`` is omitted)."""
    with _moa_notify_lock:
        if cb is None:
            _moa_notify_cbs.pop(session_key, None)
            return
        cbs = _moa_notify_cbs.get(session_key)
        if cbs:
            try:
                cbs.remove(cb)
            except ValueError:
                pass
            if not cbs:
                _moa_notify_cbs.pop(session_key, None)


def _current_moa_session_key() -> str:
    try:
        from tools.approval import get_current_session_key

        return get_current_session_key() or ""
    except Exception:
        return ""


def _notify_moa(event: str, **fields: Any) -> None:
    session_key = _current_moa_session_key()
    if not session_key:
        return
    with _moa_notify_lock:
        cbs = list(_moa_notify_cbs.get(session_key, ()))
    if not cbs:
        return
    import time as _time

    payload = {"event": event, "timestamp": _time.time(), **fields}
    for cb in cbs:
        try:
            cb(payload)
        except Exception as exc:  # noqa: BLE001 - listeners must never break the run
            logger.debug("MoA notify listener error: %s", exc)

# Configuration for MoA processing
# Reference models - these generate diverse initial responses in parallel.
# Keep this list aligned with current top-tier OpenRouter frontier options.
REFERENCE_MODELS = [
    "anthropic/claude-opus-4.6",
    "google/gemini-2.5-pro",
    "openai/gpt-5.4-pro",
    "deepseek/deepseek-v3.2",
]

# Aggregator model - synthesizes reference responses into final output.
# Prefer the strongest synthesis model in the current OpenRouter lineup.
AGGREGATOR_MODEL = "anthropic/claude-opus-4.6"

# Temperature settings optimized for MoA performance
REFERENCE_TEMPERATURE = 0.6  # Balanced creativity for diverse perspectives
AGGREGATOR_TEMPERATURE = 0.4  # Focused synthesis for consistency

# Failure handling configuration
MIN_SUCCESSFUL_REFERENCES = 1  # Minimum successful reference models needed to proceed

# =========================================================================
# Team (MoA) roster — config.yaml override
# =========================================================================
# The Settings UI writes:
#
#   moa:
#     reference_models: ["vendor/model-a", ...]
#     aggregator_model: "vendor/model-b"
#     min_successful_references: 1
#
# Explicit tool arguments win over config; config wins over the module
# constants above. Invalid entries fall back per-key so one bad field never
# disables the whole roster.


def _load_moa_config() -> Dict[str, Any]:
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        moa = cfg.get("moa")
        return moa if isinstance(moa, dict) else {}
    except Exception as exc:  # noqa: BLE001 - config is optional
        logger.debug("MoA config unavailable, using built-in roster: %s", exc)
        return {}


def resolved_moa_roster(
    reference_models: Optional[List[str]] = None,
    aggregator_model: Optional[str] = None,
) -> tuple[List[str], str]:
    """Resolve the effective roster: args > config.yaml > constants."""
    moa_cfg = _load_moa_config()

    if reference_models:
        models = [str(m).strip() for m in reference_models if str(m).strip()]
    else:
        raw_models = moa_cfg.get("reference_models")
        models = (
            [str(m).strip() for m in raw_models if str(m).strip()]
            if isinstance(raw_models, list)
            else []
        )
    if not models:
        models = list(REFERENCE_MODELS)

    explicit_aggregator = str(aggregator_model).strip() if aggregator_model else ""
    config_aggregator = str(moa_cfg.get("aggregator_model") or "").strip()
    aggregator = explicit_aggregator or config_aggregator or AGGREGATOR_MODEL
    return models, aggregator

# System prompt for the aggregator model (from the research paper)
AGGREGATOR_SYSTEM_PROMPT = """You have been provided with a set of responses from various open-source models to the latest user query. Your task is to synthesize these responses into a single, high-quality response. It is crucial to critically evaluate the information provided in these responses, recognizing that some of it may be biased or incorrect. Your response should not simply replicate the given answers but should offer a refined, accurate, and comprehensive reply to the instruction. Ensure your response is well-structured, coherent, and adheres to the highest standards of accuracy and reliability.

Responses from models:"""

_debug = DebugSession("moa_tools", env_var="MOA_TOOLS_DEBUG")


def _construct_aggregator_prompt(system_prompt: str, responses: List[str]) -> str:
    """
    Construct the final system prompt for the aggregator including all model responses.
    
    Args:
        system_prompt (str): Base system prompt for aggregation
        responses (List[str]): List of responses from reference models
        
    Returns:
        str: Complete system prompt with enumerated responses
    """
    response_text = "\n".join([f"{i+1}. {response}" for i, response in enumerate(responses)])
    return f"{system_prompt}\n\n{response_text}"


async def _run_reference_model_safe(
    model: str,
    user_prompt: str,
    temperature: float = REFERENCE_TEMPERATURE,
    max_tokens: int = 32000,
    max_retries: int = 6
) -> tuple[str, str, bool]:
    """
    Run a single reference model with retry logic and graceful failure handling.
    
    Args:
        model (str): Model identifier to use
        user_prompt (str): The user's query
        temperature (float): Sampling temperature for response generation
        max_tokens (int): Maximum tokens in response
        max_retries (int): Maximum number of retry attempts
        
    Returns:
        tuple[str, str, bool]: (model_name, response_content_or_error, success_flag)
    """
    for attempt in range(max_retries):
        try:
            logger.info("Querying %s (attempt %s/%s)", model, attempt + 1, max_retries)
            
            # Build parameters for the API call
            api_params = {
                "model": model,
                "messages": [{"role": "user", "content": user_prompt}],
                "max_tokens": max_tokens,
                "extra_body": {
                    "reasoning": {
                        "enabled": True,
                        "effort": "xhigh"
                    }
                }
            }
            
            # GPT models (especially gpt-4o-mini) don't support custom temperature values
            # Only include temperature for non-GPT models
            if not model.lower().startswith('gpt-'):
                api_params["temperature"] = temperature
            
            response = await _get_openrouter_client().chat.completions.create(**api_params)
            
            content = extract_content_or_reasoning(response)
            if not content:
                # Reasoning-only response — let the retry loop handle it
                logger.warning("%s returned empty content (attempt %s/%s), retrying", model, attempt + 1, max_retries)
                if attempt < max_retries - 1:
                    await asyncio.sleep(min(2 ** (attempt + 1), 60))
                    continue
            logger.info("%s responded (%s characters)", model, len(content))
            return model, content, True
            
        except Exception as e:
            error_str = str(e)
            # Keep retry-path logging concise; full tracebacks are reserved for
            # terminal failure paths so long-running MoA retries don't flood logs.
            if "invalid" in error_str.lower():
                logger.warning("%s invalid request error (attempt %s): %s", model, attempt + 1, error_str)
            elif "rate" in error_str.lower() or "limit" in error_str.lower():
                logger.warning("%s rate limit error (attempt %s): %s", model, attempt + 1, error_str)
            else:
                logger.warning("%s unknown error (attempt %s): %s", model, attempt + 1, error_str)

            if attempt < max_retries - 1:
                # Exponential backoff for rate limiting: 2s, 4s, 8s, 16s, 32s, 60s
                sleep_time = min(2 ** (attempt + 1), 60)
                logger.info("Retrying in %ss...", sleep_time)
                await asyncio.sleep(sleep_time)
            else:
                error_msg = f"{model} failed after {max_retries} attempts: {error_str}"
                logger.error("%s", error_msg, exc_info=True)
                return model, error_msg, False


async def _run_aggregator_model(
    system_prompt: str,
    user_prompt: str,
    temperature: float = AGGREGATOR_TEMPERATURE,
    max_tokens: int = None
) -> str:
    """
    Run the aggregator model to synthesize the final response.
    
    Args:
        system_prompt (str): System prompt with all reference responses
        user_prompt (str): Original user query
        temperature (float): Focused temperature for consistent aggregation
        max_tokens (int): Maximum tokens in final response
        
    Returns:
        str: Synthesized final response
    """
    logger.info("Running aggregator model: %s", AGGREGATOR_MODEL)

    # Build parameters for the API call
    api_params = {
        "model": AGGREGATOR_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": max_tokens,
        "extra_body": {
            "reasoning": {
                "enabled": True,
                "effort": "xhigh"
            }
        }
    }

    # GPT models (especially gpt-4o-mini) don't support custom temperature values
    # Only include temperature for non-GPT models
    if not AGGREGATOR_MODEL.lower().startswith('gpt-'):
        api_params["temperature"] = temperature

    response = await _get_openrouter_client().chat.completions.create(**api_params)

    content = extract_content_or_reasoning(response)

    # Retry once on empty content (reasoning-only response)
    if not content:
        logger.warning("Aggregator returned empty content, retrying once")
        response = await _get_openrouter_client().chat.completions.create(**api_params)
        content = extract_content_or_reasoning(response)

    logger.info("Aggregation complete (%s characters)", len(content))
    return content


async def mixture_of_agents_tool(
    user_prompt: str,
    reference_models: Optional[List[str]] = None,
    aggregator_model: Optional[str] = None
) -> str:
    """
    Process a complex query using the Mixture-of-Agents methodology.
    
    This tool leverages multiple frontier language models to collaboratively solve
    extremely difficult problems requiring intense reasoning. It's particularly
    effective for:
    - Complex mathematical proofs and calculations
    - Advanced coding problems and algorithm design
    - Multi-step analytical reasoning tasks
    - Problems requiring diverse domain expertise
    - Tasks where single models show limitations
    
    The MoA approach uses a fixed 2-layer architecture:
    1. Layer 1: Multiple reference models generate diverse responses in parallel (temp=0.6)
    2. Layer 2: Aggregator model synthesizes the best elements into final response (temp=0.4)
    
    Args:
        user_prompt (str): The complex query or problem to solve
        reference_models (Optional[List[str]]): Custom reference models to use
        aggregator_model (Optional[str]): Custom aggregator model to use
    
    Returns:
        str: JSON string containing the MoA results with the following structure:
             {
                 "success": bool,
                 "response": str,
                 "models_used": {
                     "reference_models": List[str],
                     "aggregator_model": str
                 },
                 "processing_time": float
             }
    
    Raises:
        Exception: If MoA processing fails or API key is not set
    """
    start_time = datetime.datetime.now()
    
    debug_call_data = {
        "parameters": {
            "user_prompt": user_prompt[:200] + "..." if len(user_prompt) > 200 else user_prompt,
            "reference_models": reference_models or REFERENCE_MODELS,
            "aggregator_model": aggregator_model or AGGREGATOR_MODEL,
            "reference_temperature": REFERENCE_TEMPERATURE,
            "aggregator_temperature": AGGREGATOR_TEMPERATURE,
            "min_successful_references": MIN_SUCCESSFUL_REFERENCES
        },
        "error": None,
        "success": False,
        "reference_responses_count": 0,
        "failed_models_count": 0,
        "failed_models": [],
        "final_response_length": 0,
        "processing_time_seconds": 0,
        "models_used": {}
    }
    
    try:
        logger.info("Starting Mixture-of-Agents processing...")
        logger.info("Query: %s", user_prompt[:100])
        
        # Validate API key availability
        if not os.getenv("OPENROUTER_API_KEY"):
            raise ValueError("OPENROUTER_API_KEY environment variable not set")
        
        # Use provided models or defaults (args > config.yaml > constants)
        ref_models, agg_model = resolved_moa_roster(reference_models, aggregator_model)
        
        logger.info("Using %s reference models in 2-layer MoA architecture", len(ref_models))
        
        # Layer 1: Generate diverse responses from reference models (with failure handling)
        logger.info("Layer 1: Generating reference responses...")

        async def _member_with_events(model: str):
            member_start = datetime.datetime.now()
            _notify_moa("moa.member.start", model=model)
            model_name, content, success = await _run_reference_model_safe(model, user_prompt, REFERENCE_TEMPERATURE)
            _notify_moa(
                "moa.member.done",
                model=model,
                success=bool(success),
                duration=round((datetime.datetime.now() - member_start).total_seconds(), 3),
            )
            return model_name, content, success

        model_results = await asyncio.gather(*[
            _member_with_events(model)
            for model in ref_models
        ])
        
        # Separate successful and failed responses
        successful_responses = []
        failed_models = []
        
        for model_name, content, success in model_results:
            if success:
                successful_responses.append(content)
            else:
                failed_models.append(model_name)
        
        successful_count = len(successful_responses)
        failed_count = len(failed_models)
        
        logger.info("Reference model results: %s successful, %s failed", successful_count, failed_count)
        
        if failed_models:
            logger.warning("Failed models: %s", ', '.join(failed_models))
        
        # Check if we have enough successful responses to proceed
        if successful_count < MIN_SUCCESSFUL_REFERENCES:
            raise ValueError(f"Insufficient successful reference models ({successful_count}/{len(ref_models)}). Need at least {MIN_SUCCESSFUL_REFERENCES} successful responses.")
        
        debug_call_data["reference_responses_count"] = successful_count
        debug_call_data["failed_models_count"] = failed_count
        debug_call_data["failed_models"] = failed_models
        
        # Layer 2: Aggregate responses using the aggregator model
        logger.info("Layer 2: Synthesizing final response...")
        _notify_moa("moa.aggregate.start", model=agg_model)
        aggregator_system_prompt = _construct_aggregator_prompt(
            AGGREGATOR_SYSTEM_PROMPT,
            successful_responses
        )

        final_response = await _run_aggregator_model(
            aggregator_system_prompt,
            user_prompt,
            AGGREGATOR_TEMPERATURE
        )
        _notify_moa("moa.done", success=True)
        
        # Calculate processing time
        end_time = datetime.datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        logger.info("MoA processing completed in %.2f seconds", processing_time)
        
        # Prepare successful response (only final aggregated result, minimal fields)
        result = {
            "success": True,
            "response": final_response,
            "models_used": {
                "reference_models": ref_models,
                "aggregator_model": agg_model
            }
        }
        
        debug_call_data["success"] = True
        debug_call_data["final_response_length"] = len(final_response)
        debug_call_data["processing_time_seconds"] = processing_time
        debug_call_data["models_used"] = result["models_used"]
        
        # Log debug information
        _debug.log_call("mixture_of_agents_tool", debug_call_data)
        _debug.save()
        
        return json.dumps(result, indent=2, ensure_ascii=False)
        
    except Exception as e:
        error_msg = f"Error in MoA processing: {str(e)}"
        logger.error("%s", error_msg, exc_info=True)
        
        # Calculate processing time even for errors
        end_time = datetime.datetime.now()
        processing_time = (end_time - start_time).total_seconds()

        _notify_moa("moa.done", success=False)

        # Prepare error response (minimal fields)
        result = {
            "success": False,
            "response": "MoA processing failed. Please try again or use a single model for this query.",
            "models_used": {
                "reference_models": reference_models or REFERENCE_MODELS,
                "aggregator_model": aggregator_model or AGGREGATOR_MODEL
            },
            "error": error_msg
        }
        
        debug_call_data["error"] = error_msg
        debug_call_data["processing_time_seconds"] = processing_time
        _debug.log_call("mixture_of_agents_tool", debug_call_data)
        _debug.save()
        
        return json.dumps(result, indent=2, ensure_ascii=False)


def check_moa_requirements() -> bool:
    """
    Check if all requirements for MoA tools are met.
    
    Returns:
        bool: True if requirements are met, False otherwise
    """
    return check_openrouter_api_key()



def get_moa_configuration() -> Dict[str, Any]:
    """
    Get the current MoA configuration settings.

    Returns the EFFECTIVE roster: config.yaml overrides (Settings → Team)
    applied over the module constants.
    """
    reference_models, aggregator_model = resolved_moa_roster()
    return {
        "reference_models": reference_models,
        "aggregator_model": aggregator_model,
        "reference_temperature": REFERENCE_TEMPERATURE,
        "aggregator_temperature": AGGREGATOR_TEMPERATURE,
        "min_successful_references": MIN_SUCCESSFUL_REFERENCES,
        "total_reference_models": len(reference_models),
        "failure_tolerance": f"{len(reference_models) - MIN_SUCCESSFUL_REFERENCES}/{len(reference_models)} models can fail"
    }


if __name__ == "__main__":
    """
    Simple test/demo when run directly
    """
    print("🤖 Mixture-of-Agents Tool Module")
    print("=" * 50)
    
    # Check if API key is available
    api_available = check_openrouter_api_key()
    
    if not api_available:
        print("❌ OPENROUTER_API_KEY environment variable not set")
        print("Please set your API key: export OPENROUTER_API_KEY='your-key-here'")
        print("Get API key at: https://openrouter.ai/")
        sys.exit(1)
    else:
        print("✅ OpenRouter API key found")
    
    print("🛠️  MoA tools ready for use!")
    
    # Show current configuration
    config = get_moa_configuration()
    print("\n⚙️  Current Configuration:")
    print(f"  🤖 Reference models ({len(config['reference_models'])}): {', '.join(config['reference_models'])}")
    print(f"  🧠 Aggregator model: {config['aggregator_model']}")
    print(f"  🌡️  Reference temperature: {config['reference_temperature']}")
    print(f"  🌡️  Aggregator temperature: {config['aggregator_temperature']}")
    print(f"  🛡️  Failure tolerance: {config['failure_tolerance']}")
    print(f"  📊 Minimum successful models: {config['min_successful_references']}")
    
    # Show debug mode status
    if _debug.active:
        print(f"\n🐛 Debug mode ENABLED - Session ID: {_debug.session_id}")
        print(f"   Debug logs will be saved to: ./logs/moa_tools_debug_{_debug.session_id}.json")
    else:
        print("\n🐛 Debug mode disabled (set MOA_TOOLS_DEBUG=true to enable)")
    
    print("\nBasic usage:")
    print("  from mixture_of_agents_tool import mixture_of_agents_tool")
    print("  import asyncio")
    print("")
    print("  async def main():")
    print("      result = await mixture_of_agents_tool(")
    print("          user_prompt='Solve this complex mathematical proof...'")
    print("      )")
    print("      print(result)")
    print("  asyncio.run(main())")
    
    print("\nBest use cases:")
    print("  - Complex mathematical proofs and calculations")
    print("  - Advanced coding problems and algorithm design")
    print("  - Multi-step analytical reasoning tasks")
    print("  - Problems requiring diverse domain expertise")
    print("  - Tasks where single models show limitations")
    
    print("\nPerformance characteristics:")
    print("  - Higher latency due to multiple model calls")
    print("  - Significantly improved quality for complex tasks")
    print("  - Parallel processing for efficiency")
    print(f"  - Optimized temperatures: {REFERENCE_TEMPERATURE} for reference models, {AGGREGATOR_TEMPERATURE} for aggregation")
    print("  - Token-efficient: only returns final aggregated response")
    print("  - Resilient: continues with partial model failures")
    print("  - Configurable: easy to modify models and settings at top of file")
    print("  - State-of-the-art results on challenging benchmarks")
    
    print("\nDebug mode:")
    print("  # Enable debug logging")
    print("  export MOA_TOOLS_DEBUG=true")
    print("  # Debug logs capture all MoA processing steps and metrics")
    print("  # Logs saved to: ./logs/moa_tools_debug_UUID.json")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
from tools.registry import registry

MOA_SCHEMA = {
    "name": "mixture_of_agents",
    "description": "Route a hard problem through multiple frontier LLMs collaboratively. Makes 5 API calls (4 reference models + 1 aggregator) with maximum reasoning effort — use sparingly for genuinely difficult problems. Best for: complex math, advanced algorithms, multi-step analytical reasoning, problems benefiting from diverse perspectives.",
    "parameters": {
        "type": "object",
        "properties": {
            "user_prompt": {
                "type": "string",
                "description": "The complex query or problem to solve using multiple AI models. Should be a challenging problem that benefits from diverse perspectives and collaborative reasoning."
            }
        },
        "required": ["user_prompt"]
    }
}

registry.register(
    name="mixture_of_agents",
    toolset="moa",
    schema=MOA_SCHEMA,
    handler=lambda args, **kw: mixture_of_agents_tool(user_prompt=args.get("user_prompt", "")),
    check_fn=check_moa_requirements,
    requires_env=["OPENROUTER_API_KEY"],
    is_async=True,
    emoji="🧠",
)
