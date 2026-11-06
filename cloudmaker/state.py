"""Состояние CloudMaker в файле state.json."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._dump(self._empty())

    def _empty(self) -> dict[str, Any]:
        data: dict[str, Any] = {"vms": {}}
        data["images"] = {}
        return data

    def _load(self) -> dict[str, Any]:
        raw = self.path.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
        if not isinstance(data, dict):
            data = {}
        vms = data.get("vms")
        if not isinstance(vms, dict):
            data["vms"] = {}
        images = data.get("images")
        if not isinstance(images, dict):
            data["images"] = {}
        return data

    def _dump(self, data: dict[str, Any]) -> None:
        temporary = self.path.parent / (self.path.name + ".tmp")
        temporary.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def list_vms(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(vm) for vm in self._load()["vms"].values()]

    def get_vm(self, name: str) -> dict[str, Any] | None:
        with self._lock:
            vm = self._load()["vms"].get(name)
            if vm is None:
                return None
            return dict(vm)

    def save_vm(self, vm: dict[str, Any]) -> None:
        with self._lock:
            data = self._load()
            data["vms"][vm["name"]] = vm
            self._dump(data)

    def delete_vm(self, name: str) -> None:
        with self._lock:
            data = self._load()
            data["vms"].pop(name, None)
            self._dump(data)

    def list_images(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(image) for image in self._load()["images"].values()]

    def get_image(self, name: str) -> dict[str, Any] | None:
        with self._lock:
            image = self._load()["images"].get(name)
            if image is None:
                return None
            return dict(image)

    def save_image(self, image: dict[str, Any]) -> None:
        with self._lock:
            data = self._load()
            data["images"][image["name"]] = image
            self._dump(data)

    def delete_image(self, name: str) -> None:
        with self._lock:
            data = self._load()
            data["images"].pop(name, None)
            self._dump(data)

