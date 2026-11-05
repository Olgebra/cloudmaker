"""cloud-init NoCloud: user-data, meta-data и seed ISO."""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from cloudmaker.backend import BackendError, run_cmd


class CloudInitError(Exception):
    """Некорректные user-data или параметры cloud-init."""


def render_meta_data(name: str, hostname: str) -> str:
    return "instance-id: cm-" + name + "\nlocal-hostname: " + hostname + "\n"


def render_user_data(
    hostname: str,
    ssh_key: str | None,
    user_data: str | None,
) -> str:
    """Собрать user-data.

    Облачный конфиг объединяется с hostname и ssh_authorized_keys.
    Текст, который начинается с #!, записывается как есть: hostname при этом
    всё равно попадает в meta-data.
    """
    payload: dict = {
        "hostname": hostname,
        "manage_etc_hosts": True,
    }
    if ssh_key and ssh_key.strip():
        payload["ssh_authorized_keys"] = [ssh_key.strip()]
    extra = (user_data or "").strip()
    if extra.startswith("#!"):
        if not extra.endswith("\n"):
            extra += "\n"
        return extra
    if extra:
        body = extra
        if body.startswith("#cloud-config"):
            body = body.split("\n", 1)[1] if "\n" in body else ""
        try:
            loaded = yaml.safe_load(body) if body.strip() else {}
        except yaml.YAMLError as exc:
            raise CloudInitError("user_data не является YAML: " + str(exc)) from exc
        if loaded is None:
            loaded = {}
        if not isinstance(loaded, dict):
            raise CloudInitError("user_data cloud-config должен быть словарём")
        keys: list[str] = list(payload.get("ssh_authorized_keys") or [])
        extra_keys = loaded.get("ssh_authorized_keys") or []
        if isinstance(extra_keys, str):
            extra_keys = [extra_keys]
        for key in extra_keys:
            if key not in keys:
                keys.append(key)
        payload.update(loaded)
        payload["hostname"] = hostname
        if keys:
            payload["ssh_authorized_keys"] = keys
    text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    return "#cloud-config\n" + text


def build_seed_iso(
    name: str,
    hostname: str,
    ssh_key: str | None,
    user_data: str | None,
    seed_dir: Path,
) -> Path:
    work = seed_dir / name
    work.mkdir(parents=True, exist_ok=True)
    user_path = work / "user-data"
    meta_path = work / "meta-data"
    user_path.write_text(
        render_user_data(hostname, ssh_key, user_data),
        encoding="utf-8",
    )
    meta_path.write_text(render_meta_data(name, hostname), encoding="utf-8")
    iso = seed_dir / (name + "-seed.iso")
    if iso.exists():
        iso.unlink()
    tool = shutil.which("genisoimage") or shutil.which("mkisofs")
    if tool is None:
        raise BackendError("нужен genisoimage или mkisofs, чтобы собрать seed ISO")
    run_cmd(
        [
            tool,
            "-output",
            str(iso.resolve()),
            "-V",
            "cidata",
            "-J",
            "-R",
            "user-data",
            "meta-data",
        ],
        cwd=work,
    )
    if not iso.is_file():
        raise BackendError("seed ISO не создан: " + str(iso))
    return iso
