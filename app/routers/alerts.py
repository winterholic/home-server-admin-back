from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from app.database import get_db
from app.models.alert import AlertSetting, AlertHistory
from app.schemas.alert import (
    AlertSettingItem, AlertSettingListResponse,
    AlertSettingUpdateRequest, AlertSettingCreateRequest, AlertSettingResponse,
    AlertHistoryItem, AlertHistoryResponse,
)

router = APIRouter(prefix="/api/alerts", tags=["Alert Management"])


@router.get("/settings", response_model=AlertSettingListResponse)
async def get_alert_settings(db: AsyncSession = Depends(get_db)):
    stmt = select(AlertSetting).order_by(AlertSetting.id)
    result = await db.execute(stmt)
    settings = result.scalars().all()

    return AlertSettingListResponse(
        settings=[
            AlertSettingItem(
                id=s.id,
                metric_type=s.metric_type,
                threshold=s.threshold,
                enabled=s.enabled,
                email_recipients=s.email_recipients or [],
                created_at=s.created_at.isoformat(),
                updated_at=s.updated_at.isoformat(),
            )
            for s in settings
        ]
    )


@router.put("/settings/{setting_id}", response_model=AlertSettingResponse)
async def update_alert_setting(
    setting_id: int,
    body: AlertSettingUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AlertSetting).where(AlertSetting.id == setting_id)
    result = await db.execute(stmt)
    setting = result.scalar_one_or_none()

    if not setting:
        raise HTTPException(status_code=404, detail="Alert setting not found")

    if body.threshold is not None:
        setting.threshold = body.threshold
    if body.enabled is not None:
        setting.enabled = body.enabled
    if body.email_recipients is not None:
        setting.email_recipients = body.email_recipients

    await db.commit()
    await db.refresh(setting)

    return AlertSettingResponse(
        id=setting.id,
        metric_type=setting.metric_type,
        threshold=setting.threshold,
        enabled=setting.enabled,
        email_recipients=setting.email_recipients or [],
    )


@router.post("/settings", response_model=AlertSettingResponse)
async def create_alert_setting(
    body: AlertSettingCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    setting = AlertSetting(
        metric_type=body.metric_type,
        threshold=body.threshold,
        enabled=body.enabled,
        email_recipients=body.email_recipients,
    )
    db.add(setting)
    await db.commit()
    await db.refresh(setting)

    return AlertSettingResponse(
        id=setting.id,
        metric_type=setting.metric_type,
        threshold=setting.threshold,
        enabled=setting.enabled,
    )


@router.get("/history", response_model=AlertHistoryResponse)
async def get_alert_history(
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    count_result = await db.execute(select(func.count(AlertHistory.id)))
    total = count_result.scalar() or 0

    stmt = (
        select(AlertHistory)
        .order_by(desc(AlertHistory.timestamp))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    alerts = result.scalars().all()

    return AlertHistoryResponse(
        alerts=[
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
        ],
        total=total,
    )
