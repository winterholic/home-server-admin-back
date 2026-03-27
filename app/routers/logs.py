from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from datetime import datetime, timedelta
from app.database import get_db
from app.models.log import LogHistory
from app.services.log_analyzer import get_log_statistics
from app.schemas.log import (
    LogEntry, LogListResponse, LogStatistics,
    LogTimelineResponse, TimelineBucket,
)

router = APIRouter(prefix="/api/logs", tags=["Log Management"])


@router.get("/recent", response_model=LogListResponse)
async def get_recent_logs(
    source: str | None = Query(None),
    severity: str | None = Query(None),
    log_type: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(LogHistory).order_by(desc(LogHistory.timestamp))

    if source:
        stmt = stmt.where(LogHistory.source == source)
    if severity:
        stmt = stmt.where(LogHistory.severity == severity)
    if log_type:
        stmt = stmt.where(LogHistory.log_type == log_type)

    count_stmt = select(func.count(LogHistory.id))
    if source:
        count_stmt = count_stmt.where(LogHistory.source == source)
    if severity:
        count_stmt = count_stmt.where(LogHistory.severity == severity)
    if log_type:
        count_stmt = count_stmt.where(LogHistory.log_type == log_type)

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    logs = result.scalars().all()

    return LogListResponse(
        logs=[
            LogEntry(
                id=log.id,
                timestamp=log.timestamp.isoformat(),
                log_type=log.log_type,
                severity=log.severity,
                source=log.source,
                message=log.message,
                ip_address=log.ip_address,
                count=log.count,
            )
            for log in logs
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/statistics", response_model=LogStatistics)
async def get_log_stats(
    period: str = Query("24h", pattern="^(1h|24h|7d|30d)$"),
    db: AsyncSession = Depends(get_db),
):
    hours_map = {"1h": 1, "24h": 24, "7d": 168, "30d": 720}
    hours = hours_map.get(period, 24)
    return await get_log_statistics(db, hours)


@router.get("/timeline", response_model=LogTimelineResponse)
async def get_log_timeline(
    period: str = Query("24h", pattern="^(1h|6h|24h|7d)$"),
    db: AsyncSession = Depends(get_db),
):
    hours_map = {"1h": 1, "6h": 6, "24h": 24, "7d": 168}
    hours = hours_map.get(period, 24)
    since = datetime.utcnow() - timedelta(hours=hours)

    if hours <= 1:
        bucket_minutes = 5
    elif hours <= 6:
        bucket_minutes = 15
    elif hours <= 24:
        bucket_minutes = 60
    else:
        bucket_minutes = 360

    stmt = (
        select(LogHistory)
        .where(LogHistory.timestamp >= since)
        .order_by(LogHistory.timestamp.asc())
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()

    buckets: dict[str, TimelineBucket] = {}
    for log in logs:
        minutes = (log.timestamp.minute // bucket_minutes) * bucket_minutes
        bucket_time = log.timestamp.replace(minute=minutes, second=0, microsecond=0)
        key = bucket_time.isoformat()

        if key not in buckets:
            buckets[key] = TimelineBucket(timestamp=key, total=0, errors=0, bruteforce=0)

        bucket = buckets[key]
        bucket.total += 1
        if log.severity in ("error", "critical"):
            bucket.errors += 1
        if log.log_type == "bruteforce":
            bucket.bruteforce += 1

    return LogTimelineResponse(timeline=list(buckets.values()))
