from __future__ import annotations

import json
import os
from pathlib import Path


class SettingsStore:
    """Stores user-specific application settings outside the packaged app."""

    def __init__(self, settings_path: str | Path | None = None):
        if settings_path is None:
            app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            settings_path = app_data / "FITAltitudeTool" / "settings.json"
        self.settings_path = Path(settings_path)

    def load_api_key(self) -> str | None:
        try:
            payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

        api_key = payload.get("opentopography_api_key")
        return api_key.strip() if isinstance(api_key, str) and api_key.strip() else None

    def save_api_key(self, api_key: str) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"opentopography_api_key": api_key.strip()}
        temporary_path = self.settings_path.with_suffix(".tmp")
        temporary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary_path.replace(self.settings_path)