# Android / hermes_android Rewrite Plan v6

## Goal

Rewrite `android/` (Kotlin app) and `hermes_android/` (embedded Python) so the
Android app is a **thin client over the real Hermes agent runtime**, giving mobile
users 100% of Hermes features instead of the current partial Kotlin re-implementation.

### The core architectural defect driving this rewrite

Today the app runs **two parallel agent stacks**: the embedded Python runtime
(`hermes_android` → `APIServerAdapter` → real `AIAgent`) and a hand-rolled Kotlin
agent loop (`ChatViewModel` + `NativeToolCallingChatClient`, ~2,400 LOC) that
re-implements tool dispatch, compaction, memory recall, and direct-provider calls,
bypassing the Python agent for on-device/direct chat. On-device chat silently loses
memory sync, session FTS, skill injection, compression, checkpoints, delegation,
cron, kanban, todos, MoA, usage tracking, and every future Hermes feature.

**Rule #1:** all agent execution lives in Python; Kotlin renders events. On-device
models become OpenAI-compatible providers to the agent loop.
`NativeToolCallingChatClient`, `NativeToolChatSender`, `NativeBridgeInvoker`, and the
direct-provider path in `ChatViewModel` are deleted.
**Rule #2:** one typed device-facade replaces ~30 ad-hoc `Hermes*Bridge.kt` classes.
**Rule #3:** `hermes_state.SessionDB` is the only conversation store; Kotlin caches
are read-only; no dual-write.

## Locked decisions

| # | Decision |
|---|---|
| 1 | DI: **Hilt** |
| 2 | `hermes_android` = standalone package `hermes-android` (own `pyproject.toml`/version), built from this repo, consumed by Chaquopy |
| 3 | SSH backend best-effort (Chaquopy wheel probe: asyncssh→paramiko); if neither, hidden on Android |
| 4 | Termux optional only; everything works on embedded (±proot); Termux adds pkg extras only |
| 5 | No legacy `hermes_android` API compat; repo-internal importers updated in same change |
| 6 | Assistant role + MediaProjection gated behind onboarding consent |
| 7 | All memory providers (built-in + 9 plugins) work on Android, each via in-app `post_setup()`-driven flow |
| 8 | Optional resource gauges (RAM/CPU; GPU/NPU when backends self-report) + tap-to-cleanup |

## Hard constraints (inherited; must survive)

minSdk 24 / compile+target 35 / ABIs arm64-v8a+x86_64 / universal APK; Chaquopy 17,
Python 3.13, Chaquopy-compatible deps only; pinning `>=floor,<next_major` (no bare
`>=`); `get_hermes_home()` everywhere; prompt-cache safety (deferred invalidation
default); LiteRT-LM release pin 0.16.0; release-evidence + macrobenchmark + F-Droid
reproducibility pipelines behavior-frozen (re-pointed at new layout only); hermetic
tests (no real `~/.hermes` writes).

---

## Target file/folder structure (annotated)

### `android/` — Kotlin app

```
android/
├── build.gradle.kts / settings.gradle.kts / gradle.properties   # unchanged pins; dep
│                                    additions follow pinning policy
├── fdroid/ termux*/ scripts/ release evidence/                  # pipelines untouched in
│                                    behavior; task paths re-point to new package layout
└── app/src/main/java/com/mobilefork/hermesagent/
    ├── core/
    │   ├── di/                    # Hilt modules: AppModule, RuntimeModule, DeviceModule,
    │   │                          #   NetModule (loopback clients), StoreModule
    │   ├── runtime/               # HermesRuntimeService (FGS owner), PythonHost (Chaquopy),
    │   │                          #   RuntimeState machine, BootPhaseReporter (9 phases)
    │   ├── config/                # ConfigRepository (typed over /v1/manage/config),
    │   │                          #   ProfileManager (HERMES_HOME owner), ConfigValidator
    │   ├── error/                 # HermesError sealed hierarchy, ErrorCodes (mirrors
    │   │                          #   hermes_android/errors.py), ErrorMapper(trace→typed)
    │   └── net/                   # RunsClient (/v1/runs+events SSE), ManageClient
    │                              #   (/v1/manage/*), NetworkPolicy
    ├── data/
    │   ├── db/                    # Room READ-ONLY caches: session list, tasks, kanban
    │   └── store/                 # DataStore prefs (UI-only), SecureSecretsStore (Keystore, hardened)
    ├── feature/                   # one package per screen from §UI; each = Screen + VM + repo
    │   ├── chat/                  # M03 chat, M04 drawer, M05 palette (registry-generated)
    │   ├── sessions/              # search/branch/export
    │   ├── tasks/                 # M08 running (incl. M09 inbox), M10 cron editor, M11 kanban slot
    │   ├── approvals/             # M07 sheet + notification action receiver
    │   ├── agents/                # delegation tree view
    │   ├── skills/                # M12 installed, M13 hub, curator card + editor
    │   ├── team/                  # M06 team mode components + M18 roster settings
    │   ├── tools/                 # tool explorer (schema, availability, test-invoke)
    │   ├── models/                # M17 models; backend/ (moved OnDeviceBackendManager,
    │   │                          #   LiteRtLm/LlamaCpp managers — serve loopback /v1)
    │   ├── providers/             # M16 providers + OAuth via Custom Tabs
    │   ├── mcp/                   # MCP servers list/add/test/remove
    │   ├── memory/                # M19 browser + per-provider setup flows
    │   ├── cron/  kanban/  channels/   # editors; boards; M14 platform cards+pairing
    │   ├── terminal/              # M23 terminal v2 (session tabs)
    │   ├── files/                 # M24 workspace browser + SAF grants
    │   ├── device/                # M21 device & system, Linux chooser/health
    │   ├── resources/             # gauge chip, M20 sheet, ResourceMonitor,
    │   │                          #   CleanupOrchestrator (calls /manage/system/*)
    │   ├── insights/              # M22 usage/cost charts
    │   ├── help/                  # help hub (maps /help)
    │   └── settings/              # M15 root + sub-screens per Settings map
    ├── device/facade/             # Kotlin impls of device proxy: terminal, file_io,
    │                              #   system, accessibility, projection, sensors/location/
    │                              #   calendar/logcat/notifications, clipboard, share,
    │                              #   tts, stt, notifications, apps, resources, cleanup
    ├── assistant/                 # Assistant role entry + voice session (consent-gated)
    ├── share/                     # ACTION_SEND targets → seeded conversation
    ├── tiles/  widgets/           # QS tiles; Glance widgets (chat/tasks/kanban)
    └── ui/                        # shell (NavigationSuiteScaffold), theme, components
```

**Deleted in rewrite:** `ui/chat/NativeToolCallingChatClient.kt`,
`ui/chat/NativeToolChatSender.kt`, `ui/chat/NativeBridgeInvoker.kt`,
direct-provider code path in `ChatViewModel`, `ConversationStore` as owner,
`device/Hermes*Bridge.kt` one-off classes (merged into `device/facade/`),
boot fake-delay logic.

### `hermes_android/` — standalone Python package `hermes-android`

```
hermes_android/
├── pyproject.toml                 # standalone package, own version; src layout
├── README.md
├── src/hermes_android/
│   ├── __init__.py                # __version__, public entry (start/stop/status)
│   ├── errors.py                  # HermesError hierarchy + stable string codes
│   ├── runtime/
│   │   ├── service.py             # RuntimeService — THE Kotlin entry (PyObject)
│   │   ├── bootstrap.py           # 9-phase bootstrap, emits boot.phase events
│   │   └── lifecycle.py           # asyncio-loop ownership, restart handshake
│   ├── linux/
│   │   ├── base.py                # LinuxSubsystem ABC, HealthStatus, errors
│   │   ├── embedded.py            # default: bundled busybox/native libs (no Termux)
│   │   ├── proot.py               # proot-distro userland mgmt
│   │   ├── termux.py              # optional enhancement path
│   │   ├── health.py              # 30 s tick → events
│   │   └── state.py               # versioned state.json schema
│   ├── device/
│   │   ├── facade.py              # typed protocol; calls Kotlin proxy proxies
│   │   └── registry.py            # register_facade(); fresh capability snapshots
│   ├── api/
│   │   ├── app.py                 # wires APIServerAdapter + registers manage routes
│   │   ├── manage/                # sessions.py memory.py config.py providers.py
│   │   │                          # models.py skills.py cron.py kanban.py mcp.py
│   │   │                          # profiles.py plugins.py linux.py device.py
│   │   │                          # system.py (logs/insights/debug/resources/cleanup)
│   │   ├── events.py              # clarify.request/response, moa.member.*,
│   │   │                          # delegate attribution, device.progress fanout
│   │   └── versioning.py          # bridge_version handshake; UNSUPPORTED_BRIDGE
│   ├── profile/manager.py         # HERMES_HOME glue (delegates to core profiles)
│   └── providers/android_local.py # LiteRT-LM/llama.cpp provider-profile registration
└── tests/                         # package-local unit tests (hermetic)
```

Repo-level notes: `scripts/*.py`, `tests/`, and build tasks importing old
`hermes_android.*` module paths are updated in the same change (decision 5). Core
gateway/`tools/` files are NOT modified except the explicitly listed protocol
additions (moa progress hook, clarify api wiring, delegate attribution).

---

## Wire protocol (verified on `gateway/platforms/api_server.py`)

**Agent channel (existing):** `POST /v1/runs`; `GET /v1/runs/{id}/events` (SSE:
deltas, `hermes.tool.progress(toolCallId,status)`, `approval.request` with
once/session/always/deny, `approval.responded`, usage, finish);
`POST /v1/runs/{id}/approval(choice, resolve_all)`; `.../stop`; `GET /v1/runs/{id}`;
`/v1/capabilities`; `/health/detailed`; session headers. Loopback+key default; LAN
opt-in.

**Extensions (new; same aiohttp app):**

| Addition | Purpose |
|---|---|
| `clarify.request` event + `POST /v1/runs/{id}/clarify` | approval-mirror plumbing via `clarify_gateway`; bottom-sheet + notif fallback |
| `moa.member.start\|delta\|done`, `moa.aggregate.start` events | parallel member cards |
| `parent_task_id`/`depth` on tool-progress | delegation tree |
| `device.progress` events | long device ops spinner text |
| `POST /v1/runs/{id}/steer`, `.../queue` | busy-mode composer |

**Management channel (new):** `:loopback/v1/manage/*` — sessions (list/get/FTS5/
branch/delete/export), memory, config (returns `applies: now|next_session`),
providers+OAuth, models, skills(+hub+taps+curator), cron, kanban, mcp, profiles
(switch = restart handshake), plugins, linux, device (fresh versioned capability
snapshot), system (logs/insights/debug/**resources**/**cleanup**). Every response
carries `bridge_version`.

## Resource gauges (decision 8)

Stock Android exposes per-process RAM/CPU reliably; **per-app GPU/NPU counters are
not exposed by any public stock API** — GPU/NPU rows appear only when backends
self-report (LiteRT-LM delegate stats / llama.cpp metrics); otherwise hidden with an
explanation line. Never fabricate numbers.

Aggregation: `app` + `python` (manage endpoint RSS/threads) + `local model` +
`linux` subsystem RSS. Presentation: collapsible gauge chip in chat app bar
(toggleable, Settings→Display); tap → M20 sheet; long-press → M21 Device screen.
Poll 2 s visible / 5 s chip.

Cleanup (`POST /v1/manage/system/cleanup`): Python `gc.collect()`, drop idle
auxiliary clients, trim tool-result storage; Kotlin clears image caches, voice
scratch, orphan HTTP scopes; unload idle local-model context (server kept warm
until 15 min idle); kill orphan/idle subsystem shells. Returns
`{freed_mb, per_component, skipped[]}`; never aborts a running agent.

## Boot sequence (phases + failure semantics)

1 `profile` → 2 `interp` (+sys.path shim) → 3 `config` → 4 `assets`(delta sync)
→ 5 `linux` probe → 6 `mcp` config → 7 `memory` init → 8 `api` start → 9 `ready`.
Fatal: 1,2,3,8. Degraded-continue: 4 (read-only bundled), 5 (embedded), 6, 7.
Each phase emits `boot.phase` + timing; UI M01 renders real progress.

## Device facade contract

Called from agent executor threads; Kotlin dispatches internally; bounded timeouts;
cancellation via `run_id`; errors → `HermesError` codes (`DEVICE_UNAVAILABLE`,
`PERMISSION_MISSING`, `FACADE_TIMEOUT`, `CONSENT_DENIED`, …).

## Local models as providers

Kotlin managers own download/verify/load/loopback-port. At boot `android_local.py`
registers provider profiles (last-writer-wins) with capability flags from the
verified catalog. Model switch → manage API → cache-aware apply. Chat never bypasses
the agent loop.

## Linux degraded-mode matrix (decision 4)

| Capability | Embedded (default) | +proot | +Termux (optional) |
|---|---|---|---|
| terminal/process | ✓ busybox | ✓ distro | ✓ + `pkg` |
| execute_code | ✓ | ✓ | ✓ |
| system pkg install | ✗ | ✓ apt | ✓ `pkg` |
| cron/kanban/memory/skills/MoA/delegation | ✓ | ✓ | ✓ |

---

## UI / navigation + mockups

Chat-first; single activity; type-safe Navigation in `NavigationSuiteScaffold`
(bottom bar <600 dp, rail ≥600 dp, permanent drawer ≥1200 dp); chat dual-pane ≥900 dp.
Global run banner (M28) above all screens.

Top-level tabs: **Chat** (M03, drawer M04, palette M05) · **Tasks** (M08 Running,
M09 Inbox, M10 cron editor + M11 kanban) · **Skills** (M12 installed, M13 hub,
curator card) · **Channels** (M14) · **Settings** (M15 → M16 providers, M17 models,
M18 team roster, M19 memory, M21 device, M22 insights, M25 developer, M26 profiles,
M27 backup, …). Onboarding M02; boot M01.

Settings map covers all config sections: Providers&Auth · Models (+auxiliary) ·
Team(MoA) · Tools&Toolsets · Voice&Media · Memory · Automation · Device&System ·
Security&Privacy · Personalization · Profiles · Developer · About&Updates.

### M01 Boot
```
┌──────────────────────────────────┐
│            ⟡ Hermes              │
│  Starting runtime                │
│  ▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░  62%       │
│  ✓ profile ✓ interpreter ✓ config│
│  ✓ skills synced (hash ok)       │
│  ▸ linux subsystem (proot)       │
│  · mcp · memory · api · health   │
└──────────────────────────────────┘
```
### M02 Onboarding (consent)
```
┌──────────────────────────────────┐
│ Set up Hermes              2 / 5 │
│ Choose your model                │
│ ◉ Cloud (OpenRouter…)  ○ On-device│
│ ┌ ℹ Optional: Assistant role +   │
│ │ screen context. [Learn more]   │
│ │ [ Not now ]      [ Enable ]    │
│ └─────────────────────────────── │
│              [ Continue ]        │
└──────────────────────────────────┘
```
### M03 Chat
```
┌──────────────────────────────────┐
│ ☰ Trip planning  ◔62% ▮▮38%  ⋮  │ ← ctx ring + gauge chip
│ ┌ You ─────────────────────────┐ │
│ │ Plan 5 days in Kyoto         │ │
│ └──────────────────────────────┘ │
│ ▍summarizing... (reasoning)      │
│ ┌ Hermes ─── Kimi K3 ──────────┐ │
│ │ Day 1: Arashiyama...         │ │
│ │ ▣ web_search "kyoto pass" ✓  │ │
│ └──────────────────────────────┘ │
│ + [Ask ▾] │ Type a message   🎙 │
└──────────────────────────────────┘
```
### M04 Sessions drawer
```
┌────────────────────────────┐
│ ⌕ Search sessions…         │
│ ● Trip planning     now    │
│ ○ Fix CI pipeline   2h     │
│ ○ Kanban triage     1d     │
│ long-press→Branch·Rename·  │
│   Share·Delete             │
│ [ + New session ]          │
└────────────────────────────┘
```
### M05 Command palette
```
┌──────────────────────────────────┐
│ ⌕ /comp▍                         │
│ ⏦ /compress Compress context…    │
│ ▤ Sessions → open                │
│ ⛭ Compact mode (Display)         │
│ ✦ skill: productivity/compress   │
└──────────────────────────────────┘
```
### M06 Team mode (MoA)
```
┌──────────────────────────────────┐
│ Team run ▸ 4 members             │
│ ┌ claude-opus-4.6 ───── ✓ ─────┐ │
│ ├ gemini-2.5-pro ──── ✓ ───────┤ │
│ ├ gpt-5.4-pro ─── streaming ▮──┤ │
│ ├ deepseek-v3.2 ─── failed ✕ ──┤ │
│ └──────────────────────────────┘ │
│ ⬢ Aggregating (opus)…            │
│ ┌ Hermes (aggregate) ──────────┐ │
│ │ Consensus: saga + outbox...  │ │
└──────────────────────────────────┘
```
### M07 Approval sheet
```
┌──────────────────────────────────┐
│ ╔═ Approval requested ═════════╗ │
│ ║ terminal: rm -rf build/      ║ │
│ ║ reason: destructive rm       ║ │
│ ║ [Deny] [Once] [Session] [⧗]  ║ │ ← ⧗=always, biometric
│ ╚══════════════════════════════╝ │
└──────────────────────────────────┘
```
### M08 Tasks→Running
```
┌──────────────────────────────────┐
│ Tasks  Running|Inbox 2|Schedules │
│ ● Nightly digest   04:12  Stop   │
│   └ bg run · cron/daily-7am      │
│ ● Refactor parser  00:48  Stop   │
│   └ delegate ×2 [scan ✓][test ▮] │
│ ◌ Idle — nothing else running    │
└──────────────────────────────────┘
```
### M09 Tasks→Inbox
```
┌──────────────────────────────────┐
│ Inbox                            │
│ ┌ Approval · rm -rf… [Deny][OK]┐ │
│ ├ Clarify · "which distro?"    ┤ │
│ │ ○ ubuntu ○ debian ○ other…   │ │
│ └──────────────────────────────┘ │
└──────────────────────────────────┘
```
### M10 Cron editor
```
┌──────────────────────────────────┐
│ Cron · daily digest              │
│ [ every ] [1d ▾] or 0 7 * * * ✓  │
│ Prompt "Summarize unread…"       │
│ Model: default ▾  Skills: +      │
│ Delivery: notify ▾               │
│ [Run now] [Pause]    [ Save ]    │
└──────────────────────────────────┘
```
### M11 Kanban
```
┌──────────────────────────────────┐
│ Board: main      dispatch on ⣿   │
│ Todo(2) │ Doing(1) │ Done(14)    │
│ [Rotate certs][Agent-A]          │
│ [Postgres tune][unassigned]      │
│ Doing "Provision GPU" heartbeat  │
│ + Create task                    │
└──────────────────────────────────┘
```
### M12 Skills→Installed
```
┌──────────────────────────────────┐
│ Skills  Installed|Hub|Curator    │
│ ✓ github PR workflow   bundled   │
│ ✓ codebase inspection  bundled   │
│ ◌ obsidian             optional  │
│ ✎ my-deploy-helper     agent     │
│ Curator: 3 stale → archive? [>]  │
└──────────────────────────────────┘
```
### M13 Skills→Hub
```
┌──────────────────────────────────┐
│ ⌕ Hub · categories ▾ taps(1)     │
│ productivity·maps      [Install] │
│ research·arxiv         [Install] │
│ detail: README·platforms·tools → │
└──────────────────────────────────┘
```
### M14 Channels
```
┌──────────────────────────────────┐
│ Channels          ⟳ gateway on   │
│ ● Telegram  paired · running     │
│ ● Webhook   listening :8642      │
│ ○ Slack     not configured  [>]  │
│ ⚠ Email     auth failed [Retry]  │
│ [ Restart gateway ]              │
└──────────────────────────────────┘
```
### M15 Settings root
```
┌──────────────────────────────────┐
│ Settings                         │
│ Providers & Auth              >  │
│ Models (cloud + on-device)    >  │
│ Team (MoA roster)             >  │
│ Tools & Toolsets              >  │
│ Voice & Media                 >  │
│ Memory                        >  │
│ Automation (cron/kanban)      >  │
│ Device & System               >  │
│ Security & Privacy            >  │
│ Personalization               >  │
│ Profiles                      >  │
│ Developer                     >  │
│ About & Updates               >  │
└──────────────────────────────────┘
```
### M16 Providers / M17 Models / M18 Team roster
```
M16: ● OpenRouter ✓ · ● Nous oauth ✓ · ○ Anthropic [Add] · pool order > · failover strip
M17: Default kimi-k3 ▾ · fallback chain ▸ · on-device: ✓ gemma-4-e2b loaded /
     ↓ qwen3.5-1.7b (rec 4GB) · auxiliary grid >
M18: Members ✓opus ✓gemini ✓gpt ＋add · Aggregator opus ▾ · Min 1 ▾ ·
     " Applies: next session "
```
### M19 Memory
```
Provider Built-in ▾ · honcho mem0 supermemory byterover hindsight… [Setup ▸]
⌕ "kyoto" → • prefers window seats [edit] · • vegan [delete] · [Retention >]
```
### M20 Resources sheet (gauge tap)
```
┌──────────────────────────────────┐
│ RAM 1.9/11.7GB ▓▓▓▓▓░ 16%        │
│ CPU 22%/8 cores ▓▓░░░░           │
│ GPU via LiteRT-LM ▓▓▓░ 71%*      │
│ NPU not exposed by device        │
│ App 214MB▓▓ Python 486MB▓▓▓▓      │
│ Local model 1.1GB▓▓▓▓▓ proot 92MB│
│ *backend-reported; stock hides   │
│ [ ✨ Free unused ] freed 312MB   │
└──────────────────────────────────┘
```
### M21 Device & System
```
[gauge strip] Linux: proot ubuntu-24.04 ●healthy [Switch ▾] · Shizuku ✓ ·
watchers ✓noti ○loc · terminal defaults · code exec >
```
### M22 Insights / M23 Terminal / M24 Files / M25 Developer / M26 Profiles / M27 Backup / M28 Run banner
```
M22: tokens ▓ 1.2M · $4.17 split · top tools · runs/day ▁▂▅▃ · [Export CSV]
M23: terminal tabs ▾ · `$` pane · key row [ls][cd][ctl][paste][⌨]
M24: workspace tree · + Grant folder (SAF) · long-press share/open/diff
M25: logs agent|errors|gateway ▾ lvl · [Share debug bundle] (redacted)
M26: ●default(active) ○work ○experiments [+New] · per-profile isolation note
M27: Snapshots 3 saved [Create][Restore] · Auto-backup ✓ · excluded: models/db
M28: ▸ Agent: Fixing CI… 00:41  ⏸ ⏹     (floats over any screen)
```

Full ASCII set lives in versions above; layouts are normative for structure, not
pixels — Compose tokens come from the theme system.

---

## Legacy data migration (one-shot, P1 first-run)

ConversationStore JSON → SessionDB import (originals kept); secrets copied into new
Keystore store; AppSettings mapped onto config.yaml; downloaded models kept;
idempotent marker row; summary screen. Failure → snapshot rollback.

## Data flow / FGS policy

Agent ⇄ SSE/HTTP; CRUD ⇄ manage; lifecycle/facade ⇄ PyObject. One interpreter +
loop owned by runtime FGS; tokens only in Python credential_pool. HERMES_HOME set
once pre-interp; profile switch = restart handshake. FGS: run-active→FGS; idle 60 s
stop; channels→persistent FGS; cron-only→WorkManager; battery-exemption asked at
feature-enable time.

## Failure modes

Interpreter crash → restart backoff + typed card · model OOM → unhealthy provider +
smaller-model sheet · channel failure → card+pause/resume · MoA under-min → typed
error, no partial aggregate · facade timeout/cancel → typed code · cleanup never
kills active runs (skipped list) · migration failure → rollback.

## Phased task list

- **P0 Foundation** — Hilt; errors+codes; ProfileManager; `hermes-android` package
  skeleton; repo importer updates; Kotlin agent-loop deletion; boot stub green.
- **P1 Runtime+chat parity** — boot phases (M01); runs/SSE client; approval+clarify;
  sessions on SessionDB + drawer (M04); migration; on-device providers; Team basic;
  gauge chip RAM/CPU.
- **P2 Linux+facade** — subsystems+health (M21); facade registry; bridge migration;
  SSH probe; resources endpoint+cleanup.
- **P3 Feature screens** — Tasks hub (M08–M11); agents tree; Skills+Hub+Curator
  (M12–M13); MoA parallel streaming (M06); Memory ×10 (M19); Cron (M10); Insights
  (M22); Files (M24); Terminal (M23); Developer (M25); Resources sheet (M20);
  palette (M05).
- **P4 Channels** — GatewayService; platform cards (M14); notification actions;
  steer/queue + busy composer.
- **P5 Ecosystem** — assistant role; share targets; tiles; widgets; shortcuts;
  MediaProjection consent; Auto Backup (M27); Profiles UI (M26).
- **P6 Polish** — 6-locale i18n; foldable/tablet QA; evidence repoint + green gate;
  README rewrites.

## Phase gates (100% required before next phase starts)

Gate scripts live in `android/scripts/gates/pN_*.sh` (or pytest lanes for Python);
each assertion is machine-checked; a single failure blocks the phase boundary.

**P0 gate**
1. App builds debug+release; F-Droid digest lane matches on unchanged pipeline tasks.
2. `python -m build hermes_android` produces version-pinned wheel; imports standalone.
3. Error-code parity test: every code in `hermes_android/errors.py` has an exhaustive
   `when` branch in Kotlin ErrorMapper (compile-verified).
4. HERMES_HOME invariant test: set-before-import asserted by instrumented boot.
5. Repo-wide `rg` check: zero references to deleted Kotlin classes / old python
   module paths outside allow-list; desktop `scripts/run_tests.sh` green.

**P1 gate**
1. Cold boot→`/health/detailed` 200 on API 24 + 35 emulators; all 9 `boot.phase`
   events observed; fault-inject each fatal phase → typed fatal card each time.
2. SSE turn: run emits deltas + tool.lifecycle + finish; UI renders all (instrumented).
3. Approval via sheet AND via notification action both resume the run (2 tests).
4. Clarify via choices AND free-text both resolve (2 tests).
5. SessionDB drawer: created sessions listed; FTS hit; branch copies row w/ parent ptr.
6. Migration: seeded legacy store imported; relaunch skips via marker (idempotent).
7. On-device model: tool-using task completes via agent loop (tool SSE observed).
8. MoA basic: config roster overrides tool constants; single aggregate card rendered.
9. Cache safety: `applies: next_session` patch provably leaves current system prompt
   untouched (cache-hit metric unchanged across turn).
10. Gauge chip RAM/CPU within ±10% of `dumpsys meminfo` reference sample.

**P2 gate**
1. Termux-absent device: terminal/execute_code/patch/cron-run all succeed on embedded.
2. proot device: apt install/remove of a test package succeeds.
3. Termux-present device: `pkg` extras visible AND embedded paths still pass (matrix).
4. Health monitor: kill subsystem process → degraded event ≤ 60 s; UI state flips.
5. Facade: `grep` shows zero legacy `Hermes*Bridge.kt` outside facade; every facade
   method has a contract test (happy path + typed error path).
6. Cancellation: long `terminal_exec` + run stop → process reaped ≤ timeout; typed
   FACADE_TIMEOUT path verified.
7. SSH: asyncssh OR paramiko host ls vs test container passes; else row hidden (assert).
8. Cleanup: after model load/unload cycle `freed_mb > 0`; concurrent run completes
   unaffected.

**P3 gate**
1. Every manage endpoint group has ≥1 passing contract test; screens render from
   golden fixtures (screenshot tests).
2. MoA e2e: 3-provider run → ≥3 member.start + member.done events, exactly one
   aggregate card; under-min-reference run → typed error and NO aggregate card.
3. Memory matrix: enable→setup→retain→recall→delete passes for built-in + all 9
   providers (CI uses hermetic fakes; nightly live lane opt-in marked separately).
4. Cron: created job fires within window under test alarm; Schedules shows correct
   next-run.
5. Palette index count == COMMAND_REGISTRY count (generated sync asserted).
6. Insights numbers equal Python usage store exactly for seeded fixtures.

**P4 gate**
1. Telegram adapter vs mock server: connect, receive, reply; failure card +
   pause/resume cycle tested.
2. Process-death + background: notification actions continue to drive
   approve/queue/steer correctly (instrumented).
3. Token lock: two profiles holding same platform credential → second gets typed
   lock error, no clobber.
4. 30-min screen-off soak: zero missed queue events in job log; wakelock accounting ok.

**P5 gate**
1. Assistant invocation opens voice session; consent-declined build hides all
   screen-context features (static + runtime assert).
2. Share targets: text/url/image/file each seed a conversation (4 cases).
3. Tile toggles runtime; widget + shortcut deep-link to correct destination.
4. MediaProjection: capture flows only after recorded consent; denial → CONSENT_DENIED
   card; static check: frames never logged/persisted.
5. Backup-rules XML static test: config/skills included, models + session DBs excluded.

**P6 gate**
1. 6 locales: pseudo-locale + shipped locales pass screenshot-diff on 20 key screens
   (no truncation beyond threshold).
2. Foldable/tablet: rail/drawer variants render all 5 destinations; chat dual-pane
   ≥900 dp shows both panes (screenshot tests).
3. Release evidence lane green on release build w/ updated semantics IDs;
   macrobenchmark: cold start regression ≤ 10% vs android-2026.08.20-1317 baseline.
4. Desktop `scripts/run_tests.sh` green; F-Droid reproducibility digest matches;
   README(android) + hermes-android README match final architecture.

## Validation plan (beyond gates)

Contract/golden tests per manage group; SSE fixture replay; resource-aggregator unit
math; nightly live-provider lane (opt-in) for OAuth + memory providers; soak tests
for FGS. Hermetic rule enforced everywhere.

## Out of scope

Wear OS, Android Auto, IME, desktop `computer_use`, google_meet/teams_pipeline on
Android, in-app binary self-update, camofox backend, local docker/singularity,
fabricated GPU/NPU metrics, F-Droid contract changes.
