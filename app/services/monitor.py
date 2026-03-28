import json
import os
import re
import subprocess
import psutil
import time
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.monitoring import MonitoringHistory
from app.schemas.system import (
    SystemStatusResponse, CpuStatus, MemoryStatus,
    DiskPartition, NetworkStatus,
)

_prev_net: dict | None = None
_prev_net_time: float = 0

# Filesystem types that are virtual/pseudo — skip these
_SKIP_FSTYPES = frozenset({
    'tmpfs', 'devtmpfs', 'devfs', 'iso9660', 'squashfs',
    'overlay', 'aufs', 'proc', 'sysfs', 'cgroup', 'cgroup2',
    'pstore', 'securityfs', 'debugfs', 'tracefs', 'bpf',
    'hugetlbfs', 'mqueue', 'configfs', 'fusectl', 'fuse.portal',
    'efivarfs', 'ramfs', 'rpc_pipefs', 'nfsd',
})


def _is_real_partition(part: psutil._common.sdiskpart) -> bool:
    """Return True only for real physical/logical disk partitions."""
    if part.fstype in _SKIP_FSTYPES or not part.fstype:
        return False
    skip_prefixes = ('/snap/', '/sys/', '/proc/', '/dev/', '/run/')
    if any(part.mountpoint.startswith(p) for p in skip_prefixes):
        return False
    if part.device in ('udev', 'tmpfs', 'none', 'overlay'):
        return False
    return True


def _get_physical_disk_types() -> dict[str, dict]:
    """
    Run lsblk to get physical disk info (not partitions).
    Returns {disk_basename: {"disk_type": "ssd"|"hdd"|"unknown", "label": str, "size_bytes": int}}
    """
    try:
        result = subprocess.run(
            ["lsblk", "-d", "-o", "NAME,ROTA,SIZE,MODEL", "-b", "--json"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout)
        disks: dict[str, dict] = {}
        for dev in data.get("blockdevices", []):
            name = str(dev.get("name") or "")
            rota = str(dev.get("rota") or "1")
            size = int(dev.get("size") or 0)
            model = str(dev.get("model") or "").strip()
            if not name:
                continue
            disks[name] = {
                "disk_type": "ssd" if rota == "0" else "hdd",
                "label": model or name.upper(),
                "size_bytes": size,
            }
        return disks
    except Exception:
        return {}


def _get_parent_disk_name(device: str) -> str:
    """
    Map a partition device path to its parent physical disk name.

    Examples:
      /dev/nvme0n1p3 -> nvme0n1
      /dev/sda1      -> sda
      /dev/mmcblk0p1 -> mmcblk0
      /dev/sdb       -> sdb   (already a disk, no change)
    """
    base = os.path.basename(device)

    # NVMe: nvme0n1p1 -> nvme0n1
    m = re.match(r'^(nvme\d+n\d+)p\d+$', base)
    if m:
        return m.group(1)

    # eMMC/SD: mmcblk0p1 -> mmcblk0
    m = re.match(r'^(mmcblk\d+)p\d+$', base)
    if m:
        return m.group(1)

    # SATA/IDE/virtio: sda1, vda2, hda3 -> sda, vda, hda
    m = re.match(r'^([a-z]+(?:da|db|dc|dd|de|df|dg|dh|di|dj|dk))\d+$', base)
    if m:
        return m.group(1)

    # Generic fallback: strip trailing digits
    stripped = re.sub(r'\d+$', '', base)
    return stripped if stripped else base


def collect_system_status() -> SystemStatusResponse:
    global _prev_net, _prev_net_time

    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_per_core = psutil.cpu_percent(interval=0, percpu=True)

    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    # ── Disk: aggregate partitions by physical disk ───────────────────────────
    disk_type_map = _get_physical_disk_types()   # {disk_name: {disk_type, label, size_bytes}}

    seen_mountpoints: set[str] = set()
    disk_aggregates: dict[str, dict] = {}        # {disk_name: aggregate info}

    for part in psutil.disk_partitions(all=True):
        if not _is_real_partition(part):
            continue
        if part.mountpoint in seen_mountpoints:
            continue
        seen_mountpoints.add(part.mountpoint)

        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue

        disk_name = _get_parent_disk_name(part.device)
        disk_info = disk_type_map.get(disk_name) or {
            "disk_type": "unknown",
            "label": disk_name.upper(),
            "size_bytes": 0,
        }

        if disk_name not in disk_aggregates:
            disk_aggregates[disk_name] = {
                "disk_type": disk_info["disk_type"],
                "label": disk_info["label"],
                "size_bytes": disk_info["size_bytes"],
                "used": 0,
                "free": 0,
                "primary_mountpoint": part.mountpoint,
                "primary_device": part.device,
                "primary_fstype": part.fstype,
            }

        agg = disk_aggregates[disk_name]
        agg["used"] += usage.used
        agg["free"] += usage.free
        # Prefer root mountpoint as the representative mountpoint
        if part.mountpoint == "/":
            agg["primary_mountpoint"] = "/"
            agg["primary_device"] = part.device
            agg["primary_fstype"] = part.fstype

    # Build final DiskPartition list (one entry per physical disk)
    disks: list[DiskPartition] = []
    for disk_name, agg in disk_aggregates.items():
        total = agg["size_bytes"] or (agg["used"] + agg["free"])
        if total <= 0:
            total = agg["used"] + agg["free"]
        percent = round(agg["used"] / total * 100, 1) if total > 0 else 0.0
        disks.append(DiskPartition(
            mountpoint=agg["primary_mountpoint"],
            device=f"/dev/{disk_name}",
            fstype=agg["primary_fstype"],
            total=total,
            used=agg["used"],
            free=agg["free"],
            percent=percent,
            disk_type=agg["disk_type"],
            label=agg["label"],
        ))

    # Sort: SSD first, HDD second, unknown last
    _order = {"ssd": 0, "hdd": 1, "unknown": 2}
    disks.sort(key=lambda d: _order.get(d.disk_type, 2))

    # ── Network ───────────────────────────────────────────────────────────────
    net = psutil.net_io_counters()
    now = time.time()
    rx_speed = 0.0
    tx_speed = 0.0
    if _prev_net is not None and (now - _prev_net_time) > 0:
        elapsed = now - _prev_net_time
        rx_speed = (net.bytes_recv - _prev_net["rx"]) / elapsed
        tx_speed = (net.bytes_sent - _prev_net["tx"]) / elapsed
    _prev_net = {"rx": net.bytes_recv, "tx": net.bytes_sent}
    _prev_net_time = now

    return SystemStatusResponse(
        cpu=CpuStatus(percent=cpu_percent, per_core=cpu_per_core),
        memory=MemoryStatus(
            total=mem.total,
            used=mem.used,
            available=mem.available,
            percent=mem.percent,
            swap_total=swap.total,
            swap_used=swap.used,
        ),
        disk=disks,
        network=NetworkStatus(
            rx_bytes=net.bytes_recv,
            tx_bytes=net.bytes_sent,
            rx_speed=rx_speed,
            tx_speed=tx_speed,
        ),
        uptime=int(time.time() - psutil.boot_time()),
        process_count=len(psutil.pids()),
    )


async def save_monitoring_snapshot(db: AsyncSession) -> MonitoringHistory:
    status = collect_system_status()

    # Use the primary disk (SSD or first entry) for the snapshot metric
    primary_disk_percent = status.disk[0].percent if status.disk else 0.0

    record = MonitoringHistory(
        timestamp=datetime.utcnow(),
        cpu_usage=status.cpu.percent,
        cpu_per_core=status.cpu.per_core,
        memory_total=status.memory.total,
        memory_used=status.memory.used,
        memory_percent=status.memory.percent,
        swap_used=status.memory.swap_used,
        disk_usage=[d.model_dump() for d in status.disk],
        network_rx_bytes=status.network.rx_bytes,
        network_tx_bytes=status.network.tx_bytes,
    )

    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record
