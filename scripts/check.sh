#!/usr/bin/env bash
# Единая проверка CloudMaker через curl.
# Каждая проверка печатает OK или FAIL. Сервер должен быть уже запущен:
#   uvicorn cloudmaker.main:app --host 127.0.0.1 --port 8000

set -uo pipefail

BASE="${CLOUDMAKER_URL:-http://127.0.0.1:8000}"
WORKDIR="${CLOUDMAKER_CHECK_DIR:-/tmp/cloudmaker-check}"
IMG_NAME="checkimg"
VM_NAME="checkvm"
SSH_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICheckKeyCloudMakerExample cloudmaker-check"

mkdir -p "$WORKDIR"
IMG_PATH="$WORKDIR/check-image.qcow2"

pass=0
fail=0

ok() {
  printf 'OK   %s\n' "$1"
  pass=$((pass + 1))
}

bad() {
  printf 'FAIL %s\n' "$1"
  fail=$((fail + 1))
}

expect() {
  local title="$1"
  local expected="$2"
  local needle="$3"
  shift 3
  local body code
  body="$(mktemp)"
  code="$(curl -sS -o "$body" -w '%{http_code}' "$@" || true)"
  if [[ -z "$code" ]]; then
    code="000"
  fi
  if [[ "$code" == "$expected" ]] && { [[ -z "$needle" ]] || grep -Fq -- "$needle" "$body"; }; then
    ok "$title"
  elif [[ "$code" == "$expected" ]]; then
    bad "$title (response missing: $needle)"
  else
    bad "$title (HTTP ${code}, expected ${expected})"
    if [[ -s "$body" ]]; then
      sed 's/^/    /' "$body" >&2 || true
    fi
  fi
  rm -f "$body"
}

export IMG_NAME VM_NAME WORKDIR SSH_KEY IMG_PATH

rm -f "$IMG_PATH"
if command -v qemu-img >/dev/null 2>&1; then
  qemu-img create -f qcow2 "$IMG_PATH" 64M >/dev/null
else
  : > "$IMG_PATH"
fi

curl -sS -o /dev/null -X DELETE "$BASE/vms/$VM_NAME" || true
curl -sS -o /dev/null -X DELETE "$BASE/images/$IMG_NAME" || true

expect "health" "200" "ok" "$BASE/health"

json_quota="$(python3 - "$IMG_NAME" <<'PY'
import json
import sys
print(json.dumps({
    "name": "checkvm-big",
    "image": sys.argv[1],
    "vcpus": 128,
    "memory_mb": 1024,
    "disk_gb": 1,
}))
PY
)"
expect "quota exceeded" "400" "" \
  -X POST "$BASE/vms" \
  -H "Content-Type: application/json" \
  -d "$json_quota"

json_image="$(python3 - "$IMG_NAME" "$IMG_PATH" <<'PY'
import json
import sys
print(json.dumps({
    "name": sys.argv[1],
    "path": sys.argv[2],
    "description": "образ для scripts/check.sh",
}, ensure_ascii=False))
PY
)"
expect "register image" "201" "$IMG_NAME" \
  -X POST "$BASE/images" \
  -H "Content-Type: application/json" \
  -d "$json_image"

expect "list images" "200" "$IMG_NAME" "$BASE/images"

json_vm="$(python3 - "$VM_NAME" "$IMG_NAME" "$SSH_KEY" <<'PY'
import json
import sys
print(json.dumps({
    "name": sys.argv[1],
    "image": sys.argv[2],
    "vcpus": 1,
    "memory_mb": 512,
    "disk_gb": 1,
    "hostname": sys.argv[1],
    "ssh_key": sys.argv[3],
    "user_data": "packages:\n  - curl\n",
    "network": "cloudmaker",
}, ensure_ascii=False))
PY
)"
expect "create vm" "201" "$VM_NAME" \
  -X POST "$BASE/vms" \
  -H "Content-Type: application/json" \
  -d "$json_vm"

expect "list vms" "200" "$VM_NAME" "$BASE/vms"

expect "stop vm" "200" "stopped" \
  -X POST "$BASE/vms/$VM_NAME/stop"

expect "delete vm" "200" "$VM_NAME" \
  -X DELETE "$BASE/vms/$VM_NAME"

expect "delete image" "200" "$IMG_NAME" \
  -X DELETE "$BASE/images/$IMG_NAME"

printf 'summary OK=%s FAIL=%s\n' "$pass" "$fail"
if [[ "$fail" -eq 0 ]]; then
  exit 0
fi
exit 1
