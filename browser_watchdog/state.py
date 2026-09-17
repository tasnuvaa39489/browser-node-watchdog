from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


class StateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.data: dict[str, Any] = {"instances": {}}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("instances"), dict):
                self.data = loaded
        except (OSError, ValueError):
            self.data = {"instances": {}}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def get_last_restart(self, browser_name: str) -> datetime | None:
        item = self.data.get("instances", {}).get(browser_name) or {}
        value = item.get("last_restart_at")
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    def mark_restart(self, browser_name: str, at: datetime) -> None:
        instances = self.data.setdefault("instances", {})
        item = instances.setdefault(browser_name, {})
        item["last_restart_at"] = at.isoformat()
        item["last_result"] = "RESTARTING"
        self._save()

    def mark_result(self, browser_name: str, result: str, detail: str = "") -> None:
        instances = self.data.setdefault("instances", {})
        item = instances.setdefault(browser_name, {})
        item["last_result"] = result
        item["last_detail"] = detail
        item["result_at"] = datetime.now().astimezone().isoformat()
        self._save()
