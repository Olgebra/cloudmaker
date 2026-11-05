"""Эксперимент: бэкенд VirtualBox через VBoxManage.

Временная проба вместо libvirt. Для сдачи этот модуль не нужен:
виртуальные машины должны запускаться через virsh и qemu-img.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from cloudmaker.backend import BackendError, run_cmd


class VirtualBoxBackend:
    def __init__(self, vm_folder: Path) -> None:
        self.vm_folder = vm_folder
        self.vm_folder.mkdir(parents=True, exist_ok=True)

    def create_disk(
        self,
        name: str,
        size_gb: int,
        base_image: str | None = None,
    ) -> Path:
        dest = self.vm_folder / (name + ".vdi")
        if dest.exists():
            raise BackendError("диск VirtualBox уже существует: " + str(dest))
        if base_image:
            run_cmd(
                [
                    "VBoxManage",
                    "clonemedium",
                    "disk",
                    base_image,
                    str(dest),
                    "--format",
                    "VDI",
                ]
            )
        else:
            run_cmd(
                [
                    "VBoxManage",
                    "createmedium",
                    "disk",
                    "--filename",
                    str(dest),
                    "--size",
                    str(int(size_gb) * 1024),
                    "--format",
                    "VDI",
                ]
            )
        return dest

    def start_vm(
        self,
        name: str,
        memory_mb: int,
        vcpus: int,
        disk_path: Path,
    ) -> None:
        run_cmd(
            [
                "VBoxManage",
                "createvm",
                "--name",
                name,
                "--register",
                "--basefolder",
                str(self.vm_folder),
            ]
        )
        run_cmd(
            [
                "VBoxManage",
                "modifyvm",
                name,
                "--memory",
                str(int(memory_mb)),
                "--cpus",
                str(int(vcpus)),
                "--ostype",
                "Ubuntu_64",
                "--nic1",
                "nat",
                "--boot1",
                "disk",
            ]
        )
        run_cmd(
            [
                "VBoxManage",
                "storagectl",
                name,
                "--name",
                "SATA",
                "--add",
                "sata",
            ]
        )
        run_cmd(
            [
                "VBoxManage",
                "storageattach",
                name,
                "--storagectl",
                "SATA",
                "--port",
                "0",
                "--device",
                "0",
                "--type",
                "hdd",
                "--medium",
                str(disk_path),
            ]
        )
        run_cmd(["VBoxManage", "startvm", name, "--type", "headless"])

    def stop_vm(self, name: str) -> None:
        run_cmd(["VBoxManage", "controlvm", name, "poweroff"])

    def delete_vm(self, name: str) -> None:
        subprocess.run(
            ["VBoxManage", "controlvm", name, "poweroff"],
            capture_output=True,
            text=True,
            check=False,
        )
        run_cmd(["VBoxManage", "unregistervm", name, "--delete"])

    def remove_disk(self, disk_path: str | Path) -> None:
        path = Path(disk_path)
        if path.is_file():
            path.unlink()
