from typing import Literal
from pydantic import BaseModel


ServiceType = Literal["systemd", "docker", "nohup"]
ServiceStatus = Literal["active", "inactive", "failed", "unknown"]


class ServiceInfo(BaseModel):
    name: str
    type: ServiceType
    description: str
    status: ServiceStatus
    uptime: str
    memory: int
    memory_percent: float
    pid: int | None = None
    container_id: str | None = None


class ServiceSummary(BaseModel):
    total: int
    active: int
    failed: int
    inactive: int


class ServiceListResponse(BaseModel):
    services: list[ServiceInfo]
    summary: ServiceSummary


class ServiceControlRequest(BaseModel):
    action: Literal["start", "stop", "restart", "reload"]
    service_type: ServiceType | None = None


class ServiceControlResponse(BaseModel):
    success: bool
    message: str


class ServiceLogsResponse(BaseModel):
    service_name: str
    lines: list[str]
