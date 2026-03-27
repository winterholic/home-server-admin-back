import logging
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.alert import AlertSetting, AlertHistory
from app.services.monitor import collect_system_status
from app.utils.email import send_alert_email

logger = logging.getLogger(__name__)

# Minimum minutes between repeated alerts for the same metric type.
ALERT_COOLDOWN_MINUTES = 30


async def check_alerts(db: AsyncSession) -> list[dict]:
    status = collect_system_status()
    triggered = []

    stmt = select(AlertSetting).where(AlertSetting.enabled == True)
    result = await db.execute(stmt)
    settings_list = result.scalars().all()

    if not settings_list:
        return []

    # Pre-fetch alert types that fired within the cooldown window to avoid spam.
    cooldown_since = datetime.utcnow() - timedelta(minutes=ALERT_COOLDOWN_MINUTES)
    recent_result = await db.execute(
        select(AlertHistory.alert_type)
        .where(AlertHistory.timestamp >= cooldown_since)
    )
    recent_alert_types: set[str] = {row[0] for row in recent_result.all()}

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

        # Skip if already alerted within the cooldown window.
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

        # Add to in-memory set so later iterations in the same batch respect cooldown.
        recent_alert_types.add(alert_type)

        recipients = setting.email_recipients or []
        if isinstance(recipients, list) and recipients:
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
