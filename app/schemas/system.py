from pydantic import BaseModel


class CpuStatus(BaseModel):
    percent: float
    per_core: list[float]


class MemoryStatus(BaseModel):
    total: int
    used: int
    available: int
    percent: float
    swap_total: int
    swap_used: int


class DiskPartition(BaseModel):
    mountpoint: str
    device: str
    fstype: str
    total: int
    used: int
    free: int
    percent: float
    disk_type: str = "unknown"  # "ssd", "hdd", "unknown"
    label: str = ""             # Model name or disk identifier shown in UI


class NetworkStatus(BaseModel):
    rx_bytes: int
    tx_bytes: int
    rx_speed: float
    tx_speed: float


class SystemStatusResponse(BaseModel):
    cpu: CpuStatus
    memory: MemoryStatus
    disk: list[DiskPartition]
    network: NetworkStatus
    uptime: int
    process_count: int


class SystemInfoResponse(BaseModel):
    hostname: str
    os: str
    os_version: str
    architecture: str
    processor: str
    cpu_count_physical: int | None
    cpu_count_logical: int | None
    total_memory: int
    total_swap: int
    boot_time: float


class MonitoringHistoryItem(BaseModel):
    timestamp: str
    cpu: float
    memory: float
    disk: float
    network_rx: int
    network_tx: int


class MonitoringHistoryResponse(BaseModel):
    period: str
    data: list[MonitoringHistoryItem]
