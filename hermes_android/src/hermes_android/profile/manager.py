"""Profile manager - HERMES_HOME glue (delegates to core profiles)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from hermes_android.errors import ProfileError, PROFILE_NOT_FOUND, PROFILE_SWITCH_FAILED


class ProfileManager:
    """Manages Android profiles, delegating to core profile system.

    Profiles are anchored under the app's files dir (Android has no writable
    ``~``): ``<files_dir>/profiles/<name>/hermes-home``. The active profile is
    recorded in a ``.active`` marker next to the profiles root.
    """

    def __init__(self, files_dir: str | Path | None = None):
        if files_dir is None:
            files_dir = os.environ.get("HERMES_ANDROID_FILES_DIR", "") or os.getcwd()
        self.files_dir = Path(files_dir).expanduser().resolve()
        self._active_file = self.files_dir / "profiles" / ".active"

    def _get_profiles_root(self) -> Path:
        return self.files_dir / "profiles"

    def ensure_active_profile(self, files_dir: Path) -> Path:
        """Ensure a profile is active and return its HERMES_HOME."""
        root = Path(files_dir).expanduser().resolve() / "profiles"
        active_name = self.get_active_profile_name()
        if not active_name:
            active_name = "default"

        profile_dir = root / active_name
        hermes_home = profile_dir / "hermes-home"
        hermes_home.mkdir(parents=True, exist_ok=True)
        for child in ("logs", "sessions", "skills", "downloads", "workspace"):
            (hermes_home / child).mkdir(parents=True, exist_ok=True)

        os.environ["HERMES_HOME"] = str(hermes_home)
        os.environ.setdefault("HERMES_ANDROID_FILES_DIR", str(files_dir))
        return hermes_home

    def get_active_profile_name(self) -> str | None:
        # Check environment first
        if env_profile := os.getenv("HERMES_PROFILE"):
            return env_profile

        # Check active profile marker
        if self._active_file.exists():
            try:
                name = self._active_file.read_text(encoding="utf-8").strip()
                if name:
                    return name
            except Exception:
                pass

        return None

    def set_active_profile(self, name: str) -> None:
        """Set the active profile (takes effect on next runtime start)."""
        profile_dir = self._get_profiles_root() / name
        if not profile_dir.exists():
            raise ProfileError(PROFILE_NOT_FOUND, f"Profile '{name}' does not exist")

        self._active_file.parent.mkdir(parents=True, exist_ok=True)
        self._active_file.write_text(name, encoding="utf-8")

    def list_profiles(self) -> list[dict[str, Any]]:
        """List all profiles."""
        profiles = []
        root = self._get_profiles_root()
        if root.exists():
            active = self.get_active_profile_name()
            for entry in sorted(root.iterdir()):
                if entry.is_dir() and entry.name != ".active":
                    profiles.append({
                        "name": entry.name,
                        "active": entry.name == (active or ""),
                        "path": str(entry / "hermes-home"),
                    })
        return profiles

    def create_profile(self, name: str) -> Path:
        """Create a new profile."""
        if not name or not name.isalnum():
            raise ProfileError(PROFILE_SWITCH_FAILED, "Invalid profile name")

        profile_dir = self._get_profiles_root() / name
        if profile_dir.exists():
            raise ProfileError(PROFILE_SWITCH_FAILED, f"Profile '{name}' already exists")

        hermes_home = profile_dir / "hermes-home"
        for child in ("", "logs", "sessions", "skills", "downloads", "workspace"):
            (hermes_home / child).mkdir(parents=True, exist_ok=True)

        return profile_dir

    def delete_profile(self, name: str) -> None:
        """Delete a profile."""
        if name == "default":
            raise ProfileError(PROFILE_SWITCH_FAILED, "Cannot delete default profile")

        active = self.get_active_profile_name()
        if name == active:
            raise ProfileError(PROFILE_SWITCH_FAILED, "Cannot delete active profile")

        profile_dir = self._get_profiles_root() / name
        if profile_dir.exists():
            import shutil
            shutil.rmtree(profile_dir)

    def get_profile_hermes_home(self, name: str) -> Path:
        """Get HERMES_HOME for a profile."""
        return self._get_profiles_root() / name / "hermes-home"