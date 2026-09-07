import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "hermes_android" / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from hermes_android.portals.nous import read_nous_portal_state


def test_read_nous_portal_state_defaults(monkeypatch):
    monkeypatch.setattr(
        "hermes_android.portals.nous.get_nous_auth_status",
        lambda: {
            "logged_in": False,
            "portal_base_url": None,
            "inference_base_url": None,
        },
    )

    state = read_nous_portal_state()

    assert state == {
        "portal_url": "https://portal.nousresearch.com",
        "logged_in": False,
        "inference_url": "",
    }


def test_read_nous_portal_state_prefers_auth_status_url(monkeypatch):
    monkeypatch.setattr(
        "hermes_android.portals.nous.get_nous_auth_status",
        lambda: {
            "logged_in": True,
            "portal_base_url": "https://portal-staging.nousresearch.com",
            "inference_base_url": "https://inference-api.nousresearch.com/v1",
        },
    )

    state = read_nous_portal_state()

    assert state == {
        "portal_url": "https://portal-staging.nousresearch.com",
        "logged_in": True,
        "inference_url": "https://inference-api.nousresearch.com/v1",
    }
