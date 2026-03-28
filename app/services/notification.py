import logging
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.alert import AlertSetting, AlertHistory
from app.models.settings import AppConfig
from app.services.monitor import collect_system_status
from app.utils.email import send_alert_email

logger = logging.getLogger(__name__)

ALERT_COOLDOWN_MINUTES = 30


async def _get_global_recipient(db: AsyncSession) -> str | None:
    result = await db.execute(
        select(AppConfig).where(AppConfig.key == "email_recipient")
    )
    row = result.scalar_one_or_none()
    val = row.value if row else None
    return val.strip() if val and val.strip() else None


async def check_alerts(db: AsyncSession) -> list[dict]:
    status = collect_system_status()
    triggered = []

    stmt = select(AlertSetting).where(AlertSetting.enabled == True)
    result = await db.execute(stmt)
    settings_list = result.scalars().all()

    if not settings_list:
        return []

    cooldown_since = datetime.utcnow() - timedelta(minutes=ALERT_COOLDOWN_MINUTES)
    recent_result = await db.execute(
        select(AlertHistory.alert_type)
        .where(AlertHistory.timestamp >= cooldown_since)
    )
    recent_alert_types: set[str] = {row[0] for row in recent_result.all()}

    global_recipient = await _get_global_recipient(db)

    metric_values = {
        "cpu": status.cpu.percent,
        "memory": status.memory.percent,
        "disk": max((d.percent for d in status.disk), default=0.0),
    }

    for setting in settings_list:
        current_value = metric_values.get(setting.metric_type)
        if current_value is None:
            continue

        if current_value < setting.threshold:
            continue

        alert_type = f"{setting.metric_type}_high"

        if alert_type in recent_alert_types:
            logger.debug(
                "Alert '%s' suppressed (cooldown %d min)", alert_type, ALERT_COOLDOWN_MINUTES
            )
            continue

        alert_msg = (
            f"{setting.metric_type.upper()} usage at {current_value:.1f}% "
            f"(threshold: {setting.threshold}%)"
        )

        alert = AlertHistory(
            timestamp=datetime.utcnow(),
            alert_type=alert_type,
            message=alert_msg,
            metric_value=current_value,
            sent_email=False,
        )
        db.add(alert)
        recent_alert_types.add(alert_type)

        # Use per-alert recipients if set, otherwise fall back to global recipient
        recipients: list[str] = setting.email_recipients or []
        if not recipients and global_recipient:
            recipients = [global_recipient]

        if recipients:
            try:
                await send_alert_email(
                    recipients=recipients,
                    subject=f"[NodeCtrl Alert] {setting.metric_type.upper()} Threshold Exceeded",
                    body=alert_msg,
                )
                alert.sent_email = True
            except Exception as e:
                logger.error("Failed to send alert email: %s", e)

        triggered.append({
            "type": setting.metric_type,
            "value": current_value,
            "threshold": setting.threshold,
            "message": alert_msg,
        })

    if triggered:
        await db.commit()

    return triggered
