from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.database import get_db
from app.services.monitor import collect_system_status
from app.services.service_manager import get_all_services
from app.models.alert import AlertHistory
from app.models.log import LogHistory
from app.schemas.system import SystemStatusResponse
from app.schemas.service import ServiceSummary
from app.schemas.alert import AlertHistoryItem
from app.schemas.log import LogEntry
from pydantic import BaseModel

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


class DashboardResponse(BaseModel):
    system: SystemStatusResponse
    services: ServiceSummary
    recent_alerts: list[AlertHistoryItem]
    recent_logs: list[LogEntry]


@router.get("", response_model=DashboardResponse)
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    # 1. Real-time system status
    system_status = collect_system_status()

    # 2. Service summary
    services = await get_all_services()
    service_summary = ServiceSummary(
        total=len(services),
        active=sum(1 for s in services if s.status == "active"),
        failed=sum(1 for s in services if s.status == "failed"),
        inactive=sum(1 for s in services if s.status == "inactive"),
    )

    # 3. Recent alerts (last 3)
    alert_result = await db.execute(
        select(AlertHistory)
        .order_by(desc(AlertHistory.timestamp))
        .limit(3)
    )
    alerts = alert_result.scalars().all()
    recent_alerts = [
        AlertHistoryItem(
            id=a.id,
            timestamp=a.timestamp.isoformat(),
            alert_type=a.alert_type,
            message=a.message,
            metric_value=a.metric_value,
            sent_email=a.sent_email,
            resolved_at=a.resolved_at.isoformat() if a.resolved_at else None,
        )
        for a in alerts
    ]

    # 4. Recent important log events (last 5, severity >= warning)
    log_result = await db.execute(
        select(LogHistory)
        .where(LogHistory.severity.in_(["warning", "error", "critical"]))
        .order_by(desc(LogHistory.timestamp))
        .limit(5)
    )
    logs = log_result.scalars().all()
    recent_logs = [
        LogEntry(
            id=lg.id,
            timestamp=lg.timestamp.isoformat(),
            log_type=lg.log_type,
            severity=lg.severity,
            source=lg.source,
            message=lg.message,
            ip_address=lg.ip_address,
            count=lg.count,
        )
        for lg in logs
    ]

    return DashboardResponse(
        system=system_status,
        services=service_summary,
        recent_alerts=recent_alerts,
        recent_logs=recent_logs,
    )
