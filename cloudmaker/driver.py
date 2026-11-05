"""Выбор бэкенда.

Сейчас включён эксперимент с VirtualBox (см. config.yaml, backend: virtualbox).
Рабочий вариант сдачи — libvirt, этот модуль нужно убрать.
"""

from __future__ import annotations

from pathlib import Path

from cloudmaker.config import Settings


def make_backend(settings: Settings):
    if settings.backend == "virtualbox":
        from cloudmaker.backend_vbox import VirtualBoxBackend

        return VirtualBoxBackend(Path(settings.virtualbox.vm_folder))
    from cloudmaker.backend import LibvirtBackend

    return LibvirtBackend(
        settings.libvirt.uri,
        Path(settings.storage.disks_dir),
        Path(settings.storage.xml_dir),
    )
