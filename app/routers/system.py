from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from app.database import get_db
from app.services.monitor import collect_system_status
from app.models.monitoring import MonitoringHistory
from app.utils.system_info import get_system_info
from app.schemas.system import (
    SystemStatusResponse, SystemInfoResponse,
    MonitoringHistoryResponse, MonitoringHistoryItem,
)

router = APIRouter(prefix="/api/system", tags=["System Monitoring"])


@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status():
    return collect_system_status()


@router.get("/info", response_model=SystemInfoResponse)
async def get_system_information():
    return get_system_info()


@router.get("/history", response_model=MonitoringHistoryResponse)
async def get_monitoring_history(
    period: str = Query("24h", pattern="^(1h|24h|7d|30d)$"),
    db: AsyncSession = Depends(get_db),
):
    hours_map = {"1h": 1, "24h": 24, "7d": 168, "30d": 720}
    hours = hours_map.get(period, 24)
    since = datetime.utcnow() - timedelta(hours=hours)

    stmt = (
        select(MonitoringHistory)
        .where(MonitoringHistory.timestamp >= since)
        .order_by(MonitoringHistory.timestamp.asc())
    )
    result = await db.execute(stmt)
    records = result.scalars().all()

    return MonitoringHistoryResponse(
        period=period,
        data=[
            MonitoringHistoryItem(
                timestamp=r.timestamp.isoformat(),
                cpu=r.cpu_usage,
                memory=r.memory_percent,
                disk=(
                    r.disk_usage[0]["percent"]
                    if r.disk_usage and isinstance(r.disk_usage, list)
                    else 0
                ),
                network_rx=r.network_rx_bytes,
                network_tx=r.network_tx_bytes,
            )
            for r in records
        ],
    )
