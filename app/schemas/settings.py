from pydantic import BaseModel


class SmtpSettingsRequest(BaseModel):
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_tls: bool | None = None


class MonitoringSettingsRequest(BaseModel):
    monitor_interval: int | None = None   # seconds (60-3600)
    data_retention_days: int | None = None  # days (1-365)


class AppSettingsResponse(BaseModel):
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_from: str
    smtp_tls: bool
    monitor_interval: int
    data_retention_days: int
    systemd_services: list[str]
    docker_containers: list[str]


class SmtpTestResponse(BaseModel):
    success: bool
    message: str
