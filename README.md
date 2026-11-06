# CloudMaker

Учебный мини-IaaS: создание и управление виртуальными машинами через HTTP API
на базе **QEMU/KVM** и **libvirt** (без GUI).

## Реализованные пункты задания

- **base** — запуск ВМ через `virsh` / `qemu-img` из CLI, без графического интерфейса
- **1** — HTTP API: создание / остановка / удаление ВМ
- **2** — cloud-init: `user-data`, SSH-ключ, hostname, seed ISO
- **3** — виртуальная сеть libvirt и хостовый мост `br-cloudmaker`
- **7** — реестр образов (имя, путь, описание)
- **9** — квоты CPU/RAM (`max_vcpus`, `max_memory_mb`, HTTP 400 при превышении)
- **11** — скрипт проверки `scripts/check.sh`
- **12** — скрипт очистки `scripts/cleanup.sh`

## Требования к хосту

- Linux с KVM (`/dev/kvm`); на Windows полная проверка не рассчитана
- Пакеты: `qemu-system-x86` (или `qemu-kvm`), `qemu-utils`, `libvirt-daemon`,
  `libvirt-daemon-system`, `libvirt-clients`, `genisoimage`
- Python 3.11+

Установка пакетов (Ubuntu/Debian):

```bash
sudo apt install qemu-system-x86 qemu-utils libvirt-daemon \
  libvirt-daemon-system libvirt-clients genisoimage
sudo systemctl enable --now libvirtd
sudo usermod -aG libvirt,kvm "$USER"
# затем выйти из сессии и зайти снова (или newgrp libvirt),
# чтобы uvicorn/virsh видели группу libvirt
# на других дистрибутивах имена пакетов могут отличаться
```

Проверено на Linux Mint (Ubuntu 24.04 / noble), KVM + libvirt.

Проверка KVM / libvirt:

```bash
ls -l /dev/kvm
systemctl is-active libvirtd
ls -l /var/run/libvirt/libvirt-sock
virsh -c qemu:///system list --all
```

## Установка

```bash
git clone <URL_РЕПОЗИТОРИЯ> cloudmaker
cd cloudmaker

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# при необходимости поправить пути и квоты в config.yaml
```

Скачать cloud-образ ОС на хост. Ниже — пример с Ubuntu 24.04;
можно взять другой cloud-образ (Debian, Fedora и т.д.), главное — указать его путь при регистрации через API.

```bash
mkdir -p data/images
cd data/images
wget https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img
cd ../..
```

Пример пути к образу для API: `./data/images/noble-server-cloudimg-amd64.img`.

## Запуск API

Терминал 1 — из корня репозитория запустить сервер и **не останавливать** его
(пока идут проверки во втором терминале):

```bash
source .venv/bin/activate
uvicorn cloudmaker.main:app --host 127.0.0.1 --port 8000
```

Терминал 2 — проверка живости и дальнейшие `curl` (сервер в терминале 1 должен
уже работать):

```bash
cd /путь/к/cloudmaker
source .venv/bin/activate
curl -s http://127.0.0.1:8000/health
# {"status":"ok"}
```

## Пример: образ и ВМ

Выполнять во **втором** терминале, пока в первом крутится `uvicorn`.

```bash
# 1) зарегистрировать образ (путь — реальный .qcow2 / .img на хосте)
curl -sS -X POST http://127.0.0.1:8000/images \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "ubuntu",
    "path": "./data/images/noble-server-cloudimg-amd64.img",
    "description": "Ubuntu 24.04 cloud"
  }'

# 2) создать ВМ с cloud-init и сетью
curl -sS -X POST http://127.0.0.1:8000/vms \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "demo1",
    "image": "ubuntu",
    "vcpus": 1,
    "memory_mb": 1024,
    "disk_gb": 8,
    "hostname": "demo1",
    "ssh_key": "ssh-ed25519 AAAA... your@host",
    "network": "cloudmaker"
  }'

# 3) список / стоп / удаление
curl -sS http://127.0.0.1:8000/vms
curl -sS -X POST http://127.0.0.1:8000/vms/demo1/stop
curl -sS -X DELETE http://127.0.0.1:8000/vms/demo1
```

### Если `POST /vms` падает на создании моста

Нужно, когда ответ содержит что-то вроде:

`ip link add br-cloudmaker type bridge` … `Operation not permitted`

Создание linux-моста требует прав root. Один раз подготовить мост вручную,
затем повторить `POST /vms`.

Имя моста, адрес шлюза и префикс — параметры
виртуальной сети CloudMaker из `config.yaml` (`network.bridge`, `network.gateway`,
`network.cidr`).


```bash
# задать переменные из config.yaml (не копировать слова BRIDGE/ADDR буквально в ip)
eval "$(python3 - <<'PY'
import yaml
cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
net = cfg["network"]
print(f'BRIDGE={net["bridge"]!r}')
print(f'ADDR={(net["gateway"] + "/" + net["cidr"].split("/")[1])!r}')
PY
)"
echo "BRIDGE=$BRIDGE ADDR=$ADDR"

sudo ip link add "$BRIDGE" type bridge
sudo ip link set "$BRIDGE" up
sudo ip addr replace "$ADDR" dev "$BRIDGE"
ip link show "$BRIDGE"
```

Если мост уже есть, `ip link add` может вернуть «File exists» — это нормально;
достаточно `ip link set … up` и `ip addr replace …`.

Когда мост уже поднят и адрес назначен, API больше не вызывает `ip` и может
работать **без root** (перезапустите `uvicorn` после настройки моста).

### Если `Permission denied` на диске/ISO в `/home/...`

QEMU работает от пользователя `libvirt-qemu` и не проходит по каталогам home
с правами `700`. Дать проход к проекту (подставьте свой путь):

```bash
# проход libvirt-qemu по каталогам до репозитория (подставьте свой путь к clone)
chmod o+x "$HOME"   # и при необходимости промежуточные каталоги: chmod o+x /path/to/parent
chmod -R o+rX data
```

При превышении квот из `config.yaml` (`quotas.max_vcpus` / `quotas.max_memory_mb`)
создание ВМ отвечает **HTTP 400**.

## Проверка одной командой

Сервер должен быть уже запущен:

```bash
# на всякий случай: если бит +x уже есть (ls -l показывает rwx), можно не делать
chmod +x scripts/check.sh scripts/cleanup.sh
./scripts/check.sh
```

Ожидаемый итог: строки `OK ...` и `summary OK=... FAIL=0`.

## Очистка после тестов

```bash
./scripts/cleanup.sh
```

Скрипт удаляет тестовые/оставленные домены, диски, seed ISO,
сеть `cloudmaker` и мост `br-cloudmaker` (если есть).
