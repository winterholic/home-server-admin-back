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

# Filesystem types that are virtual/pseudo and should not be shown as disk partitions
_SKIP_FSTYPES = frozenset({
    'tmpfs', 'devtmpfs', 'devfs', 'iso9660', 'squashfs',
    'overlay', 'aufs', 'proc', 'sysfs', 'cgroup', 'cgroup2',
    'pstore', 'securityfs', 'debugfs', 'tracefs', 'bpf',
    'hugetlbfs', 'mqueue', 'configfs', 'fusectl', 'fuse.portal',
    'efivarfs', 'ramfs', 'rpc_pipefs', 'nfsd',
})


def _is_real_partition(part: psutil._common.sdiskpart) -> bool:
    """Return True only for real physical/logical disk partitions."""
    if part.fstype in _SKIP_FSTYPES:
        return False
    if not part.fstype:
        return False
    # Skip snap, docker, sys, proc bind mounts
    skip_prefixes = ('/snap/', '/sys/', '/proc/', '/dev/', '/run/')
    if any(part.mountpoint.startswith(p) for p in skip_prefixes):
        return False
    # Skip virtual block devices
    if part.device in ('udev', 'tmpfs', 'none', 'overlay'):
        return False
    return True


def collect_system_status() -> SystemStatusResponse:
    global _prev_net, _prev_net_time

    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_per_core = psutil.cpu_percent(interval=0, percpu=True)

    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    disks = []
    seen_devices: set[str] = set()
    for part in psutil.disk_partitions(all=False):
        if not _is_real_partition(part):
            continue
        # Deduplicate by device path to avoid showing same physical disk twice
        device_key = part.device.split('/')[-1] if '/' in part.device else part.device
        if device_key in seen_devices:
            continue
        seen_devices.add(device_key)
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append(DiskPartition(
                mountpoint=part.mountpoint,
                device=part.device,
                fstype=part.fstype,
                total=usage.total,
                used=usage.used,
                free=usage.free,
                percent=usage.percent,
            ))
        except PermissionError:
            continue

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
