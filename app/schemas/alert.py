from pydantic import BaseModel


class AlertSettingItem(BaseModel):
    id: int
    metric_type: str
    threshold: float
    enabled: bool
    email_recipients: list[str]
    created_at: str
    updated_at: str


class AlertSettingListResponse(BaseModel):
    settings: list[AlertSettingItem]


class AlertSettingUpdateRequest(BaseModel):
    threshold: float | None = None
    enabled: bool | None = None
    email_recipients: list[str] | None = None


class AlertSettingCreateRequest(BaseModel):
    metric_type: str
    threshold: float
    enabled: bool = True
    email_recipients: list[str] = []


class AlertSettingResponse(BaseModel):
    id: int
    metric_type: str
    threshold: float
    enabled: bool
    email_recipients: list[str] = []


class AlertHistoryItem(BaseModel):
    id: int
    timestamp: str
    alert_type: str
    message: str
    metric_value: float
    sent_email: bool
    resolved_at: str | None = None


class AlertHistoryResponse(BaseModel):
    alerts: list[AlertHistoryItem]
    total: int
