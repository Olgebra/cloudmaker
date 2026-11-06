#!/usr/bin/env bash
# Идемпотентная очистка ресурсов CloudMaker:
# домены libvirt, диски, seed ISO, виртуальная сеть и хостовый мост.
# Повторный запуск завершается успехом, даже если ресурсы уже удалены.

set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

URI="qemu:///system"
STATE_FILE="./data/state.json"
DISKS_DIR="./data/disks"
SEED_DIR="./data/seeds"
XML_DIR="./data/xml"
NET_NAME="cloudmaker"
BRIDGE="br-cloudmaker"

if [[ ! -f config.yaml ]]; then
  printf '%s\n' "cleanup: config.yaml не найден, значения по умолчанию"
fi

eval "$(python3 - <<'PY'
import shlex
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

cfg = {}
path = Path("config.yaml")
if yaml is not None and path.is_file():
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(loaded, dict):
        cfg = loaded

libvirt = cfg.get("libvirt") or {}
storage = cfg.get("storage") or {}
network = cfg.get("network") or {}
values = {
    "URI": libvirt.get("uri") or "qemu:///system",
    "STATE_FILE": storage.get("state_file") or "./data/state.json",
    "DISKS_DIR": storage.get("disks_dir") or "./data/disks",
    "SEED_DIR": storage.get("seed_dir") or "./data/seeds",
    "XML_DIR": storage.get("xml_dir") or "./data/xml",
    "NET_NAME": network.get("name") or "cloudmaker",
    "BRIDGE": network.get("bridge") or "br-cloudmaker",
}
for key, value in values.items():
    print(f"{key}={shlex.quote(str(value))}")
PY
)" || true

destroy_domain() {
  local name="$1"
  if [[ -z "$name" ]]; then
    return 0
  fi
  if command -v virsh >/dev/null 2>&1; then
    virsh -c "$URI" destroy "$name" >/dev/null 2>&1 || true
    virsh -c "$URI" undefine "$name" >/dev/null 2>&1 || true
  fi
}

if [[ -f "$STATE_FILE" ]]; then
  while IFS= read -r name; do
    destroy_domain "$name"
  done < <(python3 - "$STATE_FILE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    data = {}
vms = data.get("vms") if isinstance(data, dict) else {}
if isinstance(vms, dict):
    for name in vms:
        print(name)
PY
)
fi

if [[ -d "$DISKS_DIR" ]]; then
  for disk in "$DISKS_DIR"/*.qcow2; do
    [[ -e "$disk" ]] || continue
    destroy_domain "$(basename "$disk" .qcow2)"
  done
fi

mkdir -p "$DISKS_DIR" "$SEED_DIR" "$XML_DIR"
find "$DISKS_DIR" -mindepth 1 -exec rm -rf {} + 2>/dev/null || true
find "$SEED_DIR" -mindepth 1 -exec rm -rf {} + 2>/dev/null || true
find "$XML_DIR" -mindepth 1 -exec rm -rf {} + 2>/dev/null || true

if command -v virsh >/dev/null 2>&1; then
  virsh -c "$URI" net-destroy "$NET_NAME" >/dev/null 2>&1 || true
  virsh -c "$URI" net-undefine "$NET_NAME" >/dev/null 2>&1 || true
fi

if command -v ip >/dev/null 2>&1; then
  ip link del "$BRIDGE" >/dev/null 2>&1 || true
  ip link del br-cloudmaker >/dev/null 2>&1 || true
  ip link del br-cloudmaker-typo >/dev/null 2>&1 || true
fi

python3 - "$STATE_FILE" <<'PY' || true
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = {"vms": {}, "images": {}}
if path.is_file():
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        loaded = {}
    if isinstance(loaded, dict):
        data = loaded
data["vms"] = {}
if not isinstance(data.get("images"), dict):
    data["images"] = {}
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY

printf '%s\n' "cleanup: ok"
exit 0
