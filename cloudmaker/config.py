"""Чтение config.yaml."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class LibvirtConfig(BaseModel):
    uri: str = "qemu:///system"


class StorageConfig(BaseModel):
    images_dir: str = "./data/images"
    disks_dir: str = "./data/disks"
    xml_dir: str = "./data/xml"
    state_file: str = "./data/state.json"
    seed_dir: str = "./data/seeds"


class VmDefaults(BaseModel):
    vcpus: int = 1
    memory_mb: int = 512
    disk_gb: int = 4


class NetworkConfig(BaseModel):
    name: str = "cloudmaker"
    bridge: str = "br-cloudmaker"
    cidr: str = "192.168.100.0/24"
    gateway: str = "192.168.100.1"


class Settings(BaseModel):
    libvirt: LibvirtConfig = Field(default_factory=LibvirtConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    vm: VmDefaults = Field(default_factory=VmDefaults)
    network: NetworkConfig = Field(default_factory=NetworkConfig)


def load_settings(path: str | None = None) -> Settings:
    chosen = path or os.environ.get("CLOUDMAKER_CONFIG") or "config.yaml"
    cfg_path = Path(chosen)
    if not cfg_path.is_file():
        return Settings()
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("config must be a mapping: " + str(cfg_path))
    return Settings.model_validate(raw)
