#!/bin/bash
# P0 Gate Script - Validates P0 Foundation criteria.
# Run from repo root: ./android/scripts/gates/p0_gate.sh
#
# Machine-checked assertions live in p0_gate.py. This wrapper adds the
# gradle build lanes and the desktop test suite.

set -euo pipefail

cd "$(dirname "$0")/../../.."

echo "=== P0 Gate: Foundation ==="
echo ""

echo "[1/4] Python assertions (parity, invariants, deleted-code scan)..."
python android/scripts/gates/p0_gate.py
echo ""

echo "[2/4] Building hermes-android standalone wheel..."
python -m pip wheel --no-deps --wheel-dir build/hermes-android-wheel hermes_android || {
    echo "FAIL: hermes-android wheel build failed"
    exit 1
}
WHEEL=$(ls build/hermes-android-wheel/hermes_android-*-py3-none-any.whl | head -1)
python - "$WHEEL" <<'PYEOF'
import sys, zipfile
wheel = sys.argv[1]
with zipfile.ZipFile(wheel) as zf:
    names = zf.namelist()
assert any(n == "hermes_android/__init__.py" for n in names), f"hermes_android missing from {wheel}"
assert not any(n.startswith("hermes_android/app/") for n in names), "stray app/ tree inside wheel"
print(f"  Wheel OK: {wheel} ({len(names)} entries)")
PYEOF
echo ""

echo "[3/4] Building Android app (debug)..."
./gradlew :app:assembleDebug --no-daemon -q || {
    echo "FAIL: Debug build failed"
    exit 1
}
echo "  Debug build: OK"
echo ""

echo "[4/4] Desktop test suite..."
./scripts/run_tests.sh tests/hermes_android tests/tools -q --tb=short || {
    echo "FAIL: Desktop tests failed"
    exit 1
}
echo ""

echo "=== ALL P0 GATES PASSED ==="
