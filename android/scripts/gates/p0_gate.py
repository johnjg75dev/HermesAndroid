#!/usr/bin/env python3
"""P0 Gate verification - machine-checkable foundation criteria.

Run from repo root:  python android/scripts/gates/p0_gate.py
The companion p0_gate.sh wraps this plus the gradle/desktop test lanes.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HERMES_ANDROID_SRC = REPO_ROOT / "hermes_android" / "src"
ANDROID_MAIN = REPO_ROOT / "android" / "app" / "src" / "main"

FAILURES = []


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg: str) -> None:
    print(f"OK: {msg}")


def walk(root: Path, pattern: str):
    return [p for p in root.rglob(pattern) if p.is_file()]


# ---------------------------------------------------------------------------
# Gate 2/3 support: error-code parity between hermes_android.errors and Kotlin
# ---------------------------------------------------------------------------

def load_python_error_codes() -> set[str]:
    sys.path.insert(0, str(HERMES_ANDROID_SRC))
    from hermes_android.errors import all_error_codes

    return {c.code for c in all_error_codes()}


def load_kotlin_error_codes() -> set[str]:
    kotlin_file = ANDROID_MAIN / "java/com/mobilefork/hermesagent/core/error/HermesErrorCode.kt"
    content = kotlin_file.read_text(encoding="utf-8")
    # Enum entry format:   SOME_CODE("SOME_CODE", retryable, "user message"),
    return set(re.findall(r"(?m)^\s{4}[A-Z0-9_]+\(\"([A-Z0-9_]+)\"", content))


def check_error_code_parity() -> bool:
    try:
        python_codes = load_python_error_codes()
        kotlin_codes = load_kotlin_error_codes()
    except Exception as e:
        fail(f"error code extraction failed: {e}")
        return False

    missing_in_kotlin = python_codes - kotlin_codes
    missing_in_python = kotlin_codes - python_codes

    if missing_in_kotlin or missing_in_python:
        if missing_in_kotlin:
            fail(f"error codes in Python but not Kotlin: {sorted(missing_in_kotlin)}")
        if missing_in_python:
            fail(f"error codes in Kotlin but not Python: {sorted(missing_in_python)}")
        return False
    ok(f"error code parity verified ({len(python_codes)} codes)")
    return True


def check_error_mapper_exhaustive() -> bool:
    """Every error code must have an explicit when branch in ErrorMapper."""
    mapper = ANDROID_MAIN / "java/com/mobilefork/hermesagent/core/error/ErrorMapper.kt"
    content = mapper.read_text(encoding="utf-8")
    codes = load_kotlin_error_codes()
    unhandled = sorted(
        code for code in codes
        if not re.search(rf"HermesErrorCode\.{code}\s*->", content)
    )
    if unhandled:
        fail(f"ErrorMapper missing when branches for: {unhandled}")
        return False
    ok("ErrorMapper covers every error code with an explicit when branch")
    return True


# ---------------------------------------------------------------------------
# Gate 4: HERMES_HOME invariant — profile phase owns HERMES_HOME before use
# ---------------------------------------------------------------------------

def check_hermes_home_invariant() -> bool:
    bootstrap = HERMES_ANDROID_SRC / "hermes_android" / "runtime" / "bootstrap.py"
    manager = HERMES_ANDROID_SRC / "hermes_android" / "profile" / "manager.py"
    env_mod = HERMES_ANDROID_SRC / "hermes_android" / "runtime" / "env.py"

    boot_text = bootstrap.read_text(encoding="utf-8")
    profile_idx = boot_text.find("_run_phase(BootPhase.PROFILE")
    interpreter_idx = boot_text.find("_run_phase(BootPhase.INTERPRETER")
    if profile_idx == -1 or interpreter_idx == -1 or profile_idx > interpreter_idx:
        fail("bootstrap must run the PROFILE phase first")
        return False

    mgr_text = manager.read_text(encoding="utf-8")
    ensure_idx = mgr_text.find("def ensure_active_profile")
    hermes_home_idx = mgr_text.find('os.environ["HERMES_HOME"]')
    if ensure_idx == -1 or hermes_home_idx == -1 or hermes_home_idx < ensure_idx:
        fail("ProfileManager.ensure_active_profile must set HERMES_HOME")
        return False

    env_text = env_mod.read_text(encoding="utf-8")
    if 'os.environ.get("HERMES_HOME"' not in env_text:
        fail("prepare_runtime_env must honor a pre-set HERMES_HOME (profile owner)")
        return False

    # Instrumented assertion counterpart: BootSmokeTest asserts phases order too.
    smoke = (
        REPO_ROOT / "android/app/src/androidTest/java/com/mobilefork/hermesagent/BootSmokeTest.kt"
    )
    if smoke.exists():
        smoke_text = smoke.read_text(encoding="utf-8")
        if "boot.phase" not in smoke_text and "bootPhase" not in smoke_text:
            print("NOTE: BootSmokeTest does not yet assert boot.phase events (P1 scope)")

    ok("HERMES_HOME invariant verified (profile-first boot ordering)")
    return True


# ---------------------------------------------------------------------------
# Gate 5a: zero references to deleted Kotlin classes
# ---------------------------------------------------------------------------

DELETED_KOTLIN_CLASSES = [
    "NativeToolCallingChatClient",
    "NativeToolChatSender",
    "NativeBridgeInvoker",
]


def check_no_deleted_kotlin_references() -> bool:
    violations = []
    for base in ("main", "test", "androidTest"):
        root = REPO_ROOT / "android" / "app" / "src" / base
        for path in root.rglob("*.kt"):
            text = path.read_text(encoding="utf-8")
            for cls in DELETED_KOTLIN_CLASSES:
                if cls in text:
                    violations.append(f"{path}: {cls}")
    if violations:
        for v in violations:
            fail(f"reference to deleted Kotlin class: {v}")
        return False
    ok("no references to deleted Kotlin agent-loop classes")
    return True


# ---------------------------------------------------------------------------
# Gate 5b: zero old hermes_android.* module paths anywhere in repo Python
# ---------------------------------------------------------------------------

OLD_MODULE_RE = re.compile(
    r"hermes_android\.(?:linux_assets|linux_subsystem|device_bridge|config_bridge|auth_bridge|"
    r"mobile_defaults|mcp_bridge|nous_portal_bridge|runtime_env|skills_bridge|kanban_bridge|"
    r"bundled_assets)\b"
)


def check_no_old_python_paths() -> bool:
    violations = []
    for path in walk(REPO_ROOT, "*.py"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        # The standalone package itself is the new home; skip build artifacts.
        if "/build/" in f"/{rel}" or rel.startswith("build/"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        match = OLD_MODULE_RE.search(text)
        if match:
            violations.append(f"{rel}: {match.group(0)}")
    if violations:
        for v in violations:
            fail(f"old hermes_android module path reference: {v}")
        return False
    ok("no old hermes_android module path references")
    return True


# ---------------------------------------------------------------------------
# Gate 5c: standalone package sanity — version pinning + importability
# ---------------------------------------------------------------------------

def check_standalone_package() -> bool:
    # Mirror the device environment: hermes-android wheel + hermes-agent wheel
    # (gateway, tools, ...) are both importable.
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(HERMES_ANDROID_SRC))
    try:
        import hermes_android

        version = hermes_android.__version__
        if not re.match(r"^\d+\.\d+\.\d+$", version):
            fail(f"hermes-android version is not pinned semver: {version!r}")
            return False

        import importlib

        for module in (
            "hermes_android.runtime.env",
            "hermes_android.runtime.server",
            "hermes_android.runtime.server_bridge",
            "hermes_android.runtime.bootstrap",
            "hermes_android.runtime.boot_probe",
            "hermes_android.linux.env",
            "hermes_android.config.defaults",
            "hermes_android.config.bridge",
            "hermes_android.assets.bundled",
            "hermes_android.mcp.sync",
            "hermes_android.auth.bridge",
            "hermes_android.skills.bridge",
            "hermes_android.kanban.bridge",
            "hermes_android.portals.nous",
            "hermes_android.device.proxy",
        ):
            importlib.import_module(module)

        # Root wheel must NOT ship hermes_android anymore (decision 2).
        root_pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        packages_match = re.search(
            r"\[tool\.setuptools\.packages\.find\]\s*include\s*=\s*\[(.*?)\]",
            root_pyproject,
            re.S,
        )
        if not packages_match or '"hermes_android"' in packages_match.group(1):
            fail("root wheel still packages hermes_android; it must be standalone")
            return False
    except Exception as e:
        fail(f"standalone package check failed: {e}")
        return False
    finally:
        sys.path.remove(str(REPO_ROOT))
        sys.path.remove(str(HERMES_ANDROID_SRC))
        for mod in list(sys.modules):
            if mod == "hermes_android" or mod.startswith("hermes_android."):
                del sys.modules[mod]

    ok(f"standalone hermes-android package imports (v{version}) and is excluded from the root wheel")
    return True


def main() -> int:
    checks = [
        check_error_code_parity,
        check_error_mapper_exhaustive,
        check_hermes_home_invariant,
        check_no_deleted_kotlin_references,
        check_no_old_python_paths,
        check_standalone_package,
    ]
    for check in checks:
        try:
            check()
        except Exception as e:  # noqa: BLE001 - gates must never crash silently
            fail(f"{check.__name__} raised exception: {e}")

    if FAILURES:
        print(f"\n=== {len(FAILURES)} P0 GATE CHECK(S) FAILED ===")
        return 1
    print("\n=== ALL P0 PYTHON GATES PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
