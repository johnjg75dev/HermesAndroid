# hermes-android

Android embedded runtime for Hermes Agent.

## Installation

This package is built as part of the Hermes Agent Android app build process and consumed via Chaquopy.

## Structure

```
src/hermes_android/
├── __init__.py                # __version__, public entry (start/stop/status)
├── errors.py                  # HermesError hierarchy + stable string codes
├── runtime/
│   ├── service.py             # RuntimeService — THE Kotlin entry (PyObject)
│   ├── bootstrap.py           # 9-phase bootstrap, emits boot.phase events
│   └── lifecycle.py           # asyncio-loop ownership, restart handshake
├── linux/
│   ├── base.py                # LinuxSubsystem ABC, HealthStatus, errors
│   ├── embedded.py            # default: bundled busybox/native libs (no Termux)
│   ├── proot.py               # proot-distro userland mgmt
│   ├── termux.py              # optional enhancement path
│   ├── health.py              # 30 s tick → events
│   └── state.py               # versioned state.json schema
├── device/
│   ├── facade.py              # typed protocol; calls Kotlin proxy proxies
│   └── registry.py            # register_facade(); fresh capability snapshots
├── api/
│   ├── app.py                 # wires APIServerAdapter + registers manage routes
│   ├── manage/                # sessions.py memory.py config.py providers.py
│   │                          # models.py skills.py cron.py kanban.py mcp.py
│   │                          # profiles.py plugins.py linux.py device.py
│   │                          # system.py (logs/insights/debug/resources/cleanup)
│   ├── events.py              # clarify.request/response, moa.member.*,
│   │                          # delegate attribution, device.progress fanout
│   └── versioning.py          # bridge_version handshake; UNSUPPORTED_BRIDGE
├── profile/manager.py         # HERMES_HOME glue (delegates to core profiles)
└── providers/android_local.py # LiteRT-LM/llama.cpp provider-profile registration
```

## Development

```bash
# Install in development mode
pip install -e .[dev]

# Run tests
pytest
```