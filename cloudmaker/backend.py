"""Бэкенд libvirt/QEMU.

ВМ создаются и останавливаются только командами virsh и qemu-img,
без графического интерфейса.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from xml.sax.saxutils import escape


class BackendError(RuntimeError):
    """Команда virsh или qemu-img завершилась с ошибкой."""


def run_cmd(
    cmd: list[str],
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            cwd=cwd,
        )
    except FileNotFoundError as exc:
        raise BackendError("не найдена программа: " + cmd[0]) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise BackendError(
            "команда завершилась с ошибкой: "
            + " ".join(cmd)
            + " ("
            + str(result.returncode)
            + "): "
            + detail
        )
    return result


class LibvirtBackend:
    def __init__(self, uri: str, disks_dir: Path, xml_dir: Path) -> None:
        self.uri = uri
        self.disks_dir = disks_dir
        self.xml_dir = xml_dir
        self.disks_dir.mkdir(parents=True, exist_ok=True)
        self.xml_dir.mkdir(parents=True, exist_ok=True)

    def _virsh(self, *args: str) -> subprocess.CompletedProcess[str]:
        return run_cmd(["virsh", "-c", self.uri, *args])

    def _virsh_quiet(self, *args: str) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["virsh", "-c", self.uri, *args],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise BackendError("не найдена программа: virsh") from exc

    def create_disk(
        self,
        name: str,
        size_gb: int,
        base_image: str | None = None,
    ) -> Path:
        dest = self.disks_dir / (name + ".qcow2")
        if dest.exists():
            raise BackendError("диск уже существует: " + str(dest))
        cmd = ["qemu-img", "create", "-f", "qcow2"]
        if base_image:
            cmd.extend(["-F", "qcow2", "-b", base_image])
        cmd.extend([str(dest), str(int(size_gb)) + "G"])
        try:
            run_cmd(cmd)
        except BackendError:
            if dest.is_file():
                dest.unlink()
            raise
        return dest

    def render_domain_xml(
        self,
        name: str,
        memory_mb: int,
        vcpus: int,
        disk_path: Path,
    ) -> str:
        disk = escape(str(disk_path))
        vm = escape(name)
        nic_network = escape("default")
        lines = [
            "<domain type='kvm'>",
            "  <name>" + vm + "</name>",
            "  <memory unit='MiB'>" + str(int(memory_mb)) + "</memory>",
            "  <currentMemory unit='MiB'>" + str(int(memory_mb)) + "</currentMemory>",
            "  <vcpu placement='static'>" + str(int(vcpus)) + "</vcpu>",
            '  <os>',
            "    <type arch='x86_64' machine='pc'>hvm</type>",
            "    <boot dev='hd'/>",
            '  </os>',
            '  <features>',
            '    <acpi/>',
            '    <apic/>',
            '  </features>',
            '  <on_poweroff>destroy</on_poweroff>',
            '  <on_reboot>restart</on_reboot>',
            '  <on_crash>destroy</on_crash>',
            '  <devices>',
            "    <disk type='file' device='disk'>",
            "      <driver name='qemu' type='qcow2'/>",
            "      <source file='" + disk + "'/>",
            "      <target dev='vda' bus='virtio'/>",
            '    </disk>',
        ]
        lines.extend(
            [
                "    <interface type='network'>",
                "      <source network='" + nic_network + "'/>",
                "      <model type='virtio'/>",
                "    </interface>",
                "    <serial type='pty'>",
                "      <target port='0'/>",
                "    </serial>",
                "    <console type='pty'>",
                "      <target type='serial' port='0'/>",
                "    </console>",
                "  </devices>",
                "</domain>",
                "",
            ]
        )
        return "\n".join(lines)

    def start_vm(
        self,
        name: str,
        memory_mb: int,
        vcpus: int,
        disk_path: Path,
    ) -> None:
        xml = self.render_domain_xml(name, memory_mb, vcpus, disk_path)
        xml_path = self.xml_dir / (name + ".xml")
        xml_path.write_text(xml, encoding="utf-8")
        try:
            self._virsh("define", str(xml_path))
            try:
                self._virsh("start", name)
            except BackendError:
                self._virsh_quiet("undefine", name)
                raise
        except BackendError:
            xml_path.unlink(missing_ok=True)
            raise

    def dom_state(self, name: str) -> str | None:
        result = self._virsh_quiet("domstate", name)
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def stop_vm(self, name: str) -> None:
        state = self.dom_state(name)
        if state is None:
            raise BackendError("домен не найден: " + name)
        if state != "shut off":
            self._virsh("destroy", name)

    def delete_vm(self, name: str) -> None:
        state = self.dom_state(name)
        xml_path = self.xml_dir / (name + ".xml")
        if state is None:
            xml_path.unlink(missing_ok=True)
            return
        if state != "shut off":
            self._virsh_quiet("destroy", name)
        result = self._virsh_quiet("undefine", name)
        xml_path.unlink(missing_ok=True)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise BackendError("не удалось удалить домен " + name + ": " + detail)

    def remove_disk(self, disk_path: str | Path) -> None:
        path = Path(disk_path)
        if path.is_file():
            path.unlink()

