"""HTTP API CloudMaker."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from cloudmaker.backend import BackendError, LibvirtBackend
from cloudmaker.config import load_settings
from cloudmaker.state import StateStore
from cloudmaker.cloudinit import CloudInitError, build_seed_iso, render_user_data

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
HOSTNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")

router = APIRouter()
settings = load_settings()
state = StateStore(Path(settings.storage.state_file))
backend = LibvirtBackend(
    settings.libvirt.uri,
    Path(settings.storage.disks_dir),
    Path(settings.storage.xml_dir),
)


class VmCreate(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
    image_path: str | None = Field(
        default=None,
        description="Путь к базовому qcow2, если нужен backing file",
    )
    vcpus: int | None = None
    memory_mb: int | None = None
    disk_gb: int | None = None
    hostname: str | None = Field(default=None, description="Имя хоста внутри ВМ")
    ssh_key: str | None = Field(default=None, description="Публичный SSH-ключ")
    user_data: str | None = Field(
        default=None,
        description="Дополнительный cloud-config или скрипт user-data",
    )


def _sizes(body: VmCreate) -> tuple[int, int, int]:
    vcpus = settings.vm.vcpus if body.vcpus is None else body.vcpus
    memory_mb = settings.vm.memory_mb if body.memory_mb is None else body.memory_mb
    disk_gb = settings.vm.disk_gb if body.disk_gb is None else body.disk_gb
    if vcpus < 1 or memory_mb < 1 or disk_gb < 1:
        raise HTTPException(
            status_code=400,
            detail="vcpus, memory_mb и disk_gb должны быть положительными",
        )
    return vcpus, memory_mb, disk_gb


def _remove_seed(name: str) -> None:
    seed_dir = Path(settings.storage.seed_dir)
    iso = seed_dir / (name + "-seed.iso")
    if iso.is_file():
        iso.unlink()
    work = seed_dir / name
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)


def _rollback(name: str, disk_path: Path | None) -> None:
    try:
        backend.delete_vm(name)
    except (BackendError, OSError):
        pass
    if disk_path is not None:
        backend.remove_disk(disk_path)
    _remove_seed(name)


@router.get("/vms")
def list_vms() -> dict:
    return {"vms": state.list_vms()}


@router.post("/vms", status_code=201)
def create_vm(body: VmCreate) -> dict:
    if state.get_vm(body.name) is not None:
        raise HTTPException(status_code=409, detail="ВМ уже существует")

    vcpus, memory_mb, disk_gb = _sizes(body)
    hostname = body.hostname or body.name
    if not HOSTNAME_RE.match(hostname):
        raise HTTPException(status_code=400, detail="Некорректное имя хоста")
    try:
        render_user_data(hostname, body.ssh_key, body.user_data)
    except CloudInitError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    base = body.image_path or None

    disk_path: Path | None = None
    try:
        disk_path = backend.create_disk(body.name, disk_gb, base_image=base)
        seed_iso = build_seed_iso(
            body.name,
            hostname,
            body.ssh_key,
            body.user_data,
            Path(settings.storage.seed_dir),
        )
        backend.start_vm(
            body.name,
            memory_mb,
            vcpus,
            disk_path,
            seed_iso=seed_iso,
        )
    except CloudInitError as exc:
        _rollback(body.name, disk_path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BackendError as exc:
        _rollback(body.name, disk_path)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    vm = {
        "name": body.name,
        "status": "running",
        "vcpus": vcpus,
        "memory_mb": memory_mb,
        "disk_gb": disk_gb,
        "disk_path": str(disk_path),
    }
    vm["image_path"] = base
    vm["hostname"] = hostname
    state.save_vm(vm)
    return vm


@router.post("/vms/{name}/stop")
def stop_vm(name: str) -> dict:
    vm = state.get_vm(name)
    if vm is None:
        raise HTTPException(status_code=404, detail="ВМ не найдена")
    try:
        backend.stop_vm(name)
    except BackendError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    vm["status"] = "stopped"
    state.save_vm(vm)
    return vm


@router.delete("/vms/{name}")
def delete_vm(name: str) -> dict:
    vm = state.get_vm(name)
    if vm is None:
        raise HTTPException(status_code=404, detail="ВМ не найдена")
    try:
        backend.delete_vm(name)
    except BackendError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    backend.remove_disk(vm.get("disk_path") or "")
    _remove_seed(name)
    state.delete_vm(name)
    return {"deleted": name}

