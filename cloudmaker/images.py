"""Реестр образов: имя, путь к файлу и описание.

Удаление записи не удаляет файл образа с диска.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from cloudmaker.state import StateStore

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")


class ImageError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def list_images(state: StateStore) -> list[dict[str, Any]]:
    return state.list_images()


def get_image(state: StateStore, name: str) -> dict[str, Any]:
    image = state.get_image(name)
    if image is None:
        raise ImageError("Образ не найден: " + name, 404)
    return image


def image_in_use(state: StateStore, name: str) -> bool:
    return any(vm.get("image") == name for vm in state.list_vms())


def register_image(
    state: StateStore,
    name: str,
    path: str,
    description: str,
) -> dict[str, Any]:
    if not NAME_RE.match(name):
        raise ImageError("Некорректное имя образа", 400)
    if state.get_image(name) is not None:
        raise ImageError("Образ уже зарегистрирован: " + name, 409)
    image_path = Path(path)
    if not image_path.is_file():
        raise ImageError("Файл образа не найден: " + path, 400)
    image = {
        "name": name,
        "path": str(image_path.resolve()),
        "description": description,
    }
    state.save_image(image)
    return image


def delete_image(state: StateStore, name: str) -> None:
    if state.get_image(name) is None:
        raise ImageError("Образ не найден: " + name, 404)
    state.delete_image(name)
