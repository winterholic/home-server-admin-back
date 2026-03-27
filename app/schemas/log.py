from pydantic import BaseModel


class LogEntry(BaseModel):
    id: int
    timestamp: str
    log_type: str
    severity: str
    source: str
    message: str
    ip_address: str | None = None
    count: int = 1


class LogListResponse(BaseModel):
    logs: list[LogEntry]
    total: int
    limit: int
    offset: int


class LogStatistics(BaseModel):
    total: int
    bruteforce_attempts: int
    errors: int
    by_type: dict[str, int]
    by_severity: dict[str, int]


class TimelineBucket(BaseModel):
    timestamp: str
    total: int
    errors: int
    bruteforce: int


class LogTimelineResponse(BaseModel):
    timeline: list[TimelineBucket]
