"""Виртуальная сеть libvirt и хостовый linux-мост."""

from __future__ import annotations

import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

from cloudmaker.backend import BackendError, run_cmd


class NetworkError(BackendError):
    """Не удалось подготовить мост или сеть libvirt."""


def _prefix(cidr: str) -> str:
    if "/" not in cidr:
        raise NetworkError("ожидался CIDR вида 192.168.100.0/24, получено: " + cidr)
    prefix = cidr.split("/", 1)[1]
    if not prefix.isdigit():
        raise NetworkError("некорректный CIDR: " + cidr)
    return prefix


def _bridge_exists(bridge: str) -> bool:
    result = subprocess.run(
        ["ip", "link", "show", "dev", bridge],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _bridge_is_up(bridge: str) -> bool:
    result = subprocess.run(
        ["ip", "-o", "link", "show", "dev", bridge],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    # пример: 42: br-cloudmaker: <BROADCAST,MULTICAST,UP,LOWER_UP> ...
    flags = result.stdout.upper().split("<", 1)[-1].split(">", 1)[0]
    return "UP" in flags.split(",")


def _bridge_has_addr(bridge: str, addr: str) -> bool:
    result = subprocess.run(
        ["ip", "-o", "addr", "show", "dev", bridge],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    return addr in result.stdout


def ensure_host_bridge(bridge: str, gateway: str, cidr: str) -> None:
    """Создать linux-мост на хосте и назначить адрес шлюза.

    Если мост уже поднят и адрес уже назначен (например после sudo),
    повторные вызовы ip не выполняются — это позволяет работать API без root.
    """
    wanted = gateway + "/" + _prefix(cidr)
    if (
        _bridge_exists(bridge)
        and _bridge_is_up(bridge)
        and _bridge_has_addr(bridge, wanted)
    ):
        return

    hint = (
        "Нет прав на настройку моста. Один раз выполните от root: "
        "sudo ip link add "
        + bridge
        + " type bridge; sudo ip link set "
        + bridge
        + " up; sudo ip addr replace "
        + wanted
        + " dev "
        + bridge
    )
    try:
        if not _bridge_exists(bridge):
            run_cmd(["ip", "link", "add", bridge, "type", "bridge"])
        if not _bridge_is_up(bridge):
            run_cmd(["ip", "link", "set", bridge, "up"])
        if not _bridge_has_addr(bridge, wanted):
            run_cmd(["ip", "addr", "replace", wanted, "dev", bridge])
    except BackendError as exc:
        detail = str(exc)
        if "Operation not permitted" in detail or "Permission denied" in detail:
            raise NetworkError(hint) from exc
        raise NetworkError(detail) from exc


def _net_dumpxml(uri: str, name: str) -> str | None:
    result = subprocess.run(
        ["virsh", "-c", uri, "net-dumpxml", name],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _net_active(uri: str, name: str) -> bool:
    result = subprocess.run(
        ["virsh", "-c", uri, "net-info", name],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    for line in result.stdout.splitlines():
        if line.strip().lower().startswith("active:"):
            return line.split(":", 1)[1].strip().lower().startswith("yes")
    return False


def _bridge_matches(xml: str, bridge: str) -> bool:
    return ("name='" + bridge + "'") in xml or ('name="' + bridge + '"') in xml


def ensure_libvirt_network(uri: str, name: str, bridge: str) -> None:
    """Описать сеть libvirt поверх хостового моста, запустить и включить автостарт."""
    xml = (
        "<network>\n"
        "  <name>" + escape(name) + "</name>\n"
        "  <forward mode='bridge'/>\n"
        "  <bridge name='" + escape(bridge) + "'/>\n"
        "</network>\n"
    )
    xml_path = Path("data/xml") / ("net-" + name + ".xml")
    try:
        current = _net_dumpxml(uri, name)
        if current is not None and not _bridge_matches(current, bridge):
            if _net_active(uri, name):
                run_cmd(["virsh", "-c", uri, "net-destroy", name])
            run_cmd(["virsh", "-c", uri, "net-undefine", name])
            current = None
        if current is None:
            xml_path.parent.mkdir(parents=True, exist_ok=True)
            xml_path.write_text(xml, encoding="utf-8")
            run_cmd(["virsh", "-c", uri, "net-define", str(xml_path)])
        if not _net_active(uri, name):
            run_cmd(["virsh", "-c", uri, "net-start", name])
        run_cmd(["virsh", "-c", uri, "net-autostart", name])
    except BackendError as exc:
        raise NetworkError(str(exc)) from exc


def ensure_network(uri: str, name: str, bridge: str, gateway: str, cidr: str) -> None:
    ensure_host_bridge(bridge, gateway, cidr)
    ensure_libvirt_network(uri, name, bridge)
