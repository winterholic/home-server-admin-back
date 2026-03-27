import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.config import get_settings
from app.models.settings import AppConfig
from app.schemas.settings import (
    AppSettingsResponse,
    SmtpSettingsRequest,
    MonitoringSettingsRequest,
    SmtpTestResponse,
)
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["Settings"])

# Keys stored in app_config table for overridable settings
_SMTP_KEYS = ("smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from", "smtp_tls")
_MONITOR_KEYS = ("monitor_interval", "data_retention_days")


async def _get_overrides(db: AsyncSession, keys: tuple[str, ...]) -> dict[str, str]:
    result = await db.execute(
        select(AppConfig).where(AppConfig.key.in_(keys))
    )
    return {row.key: row.value for row in result.scalars().all() if row.value is not None}


async def _upsert(db: AsyncSession, key: str, value: str) -> None:
    result = await db.execute(select(AppConfig).where(AppConfig.key == key))
    config = result.scalar_one_or_none()
    if config:
        config.value = value
    else:
        db.add(AppConfig(key=key, value=value))


@router.get("", response_model=AppSettingsResponse)
async def get_app_settings(db: AsyncSession = Depends(get_db)):
    base = get_settings()
    overrides = await _get_overrides(db, _SMTP_KEYS + _MONITOR_KEYS)

    def _str(key: str, default: str) -> str:
        return overrides.get(key, default)

    def _int(key: str, default: int) -> int:
        v = overrides.get(key)
        return int(v) if v is not None else default

    def _bool(key: str, default: bool) -> bool:
        v = overrides.get(key)
        if v is None:
            return default
        return v.lower() in ("true", "1", "yes")

    return AppSettingsResponse(
        smtp_host=_str("smtp_host", base.smtp_host),
        smtp_port=_int("smtp_port", base.smtp_port),
        smtp_user=_str("smtp_user", base.smtp_user),
        smtp_from=_str("smtp_from", base.smtp_from),
        smtp_tls=_bool("smtp_tls", base.smtp_tls),
        monitor_interval=_int("monitor_interval", base.monitor_interval),
        data_retention_days=_int("data_retention_days", base.data_retention_days),
        systemd_services=base.systemd_service_list,
        docker_containers=base.docker_container_list,
    )


@router.put("/smtp", response_model=AppSettingsResponse)
async def update_smtp_settings(
    body: SmtpSettingsRequest,
    db: AsyncSession = Depends(get_db),
):
    updates: dict[str, str] = {}
    if body.smtp_host is not None:
        updates["smtp_host"] = body.smtp_host
    if body.smtp_port is not None:
        updates["smtp_port"] = str(body.smtp_port)
    if body.smtp_user is not None:
        updates["smtp_user"] = body.smtp_user
    if body.smtp_password is not None:
        updates["smtp_password"] = body.smtp_password
    if body.smtp_from is not None:
        updates["smtp_from"] = body.smtp_from
    if body.smtp_tls is not None:
        updates["smtp_tls"] = str(body.smtp_tls).lower()

    for key, value in updates.items():
        await _upsert(db, key, value)

    await db.commit()
    return await get_app_settings(db)


@router.put("/monitoring", response_model=AppSettingsResponse)
async def update_monitoring_settings(
    body: MonitoringSettingsRequest,
    db: AsyncSession = Depends(get_db),
):
    if body.monitor_interval is not None:
        if not (60 <= body.monitor_interval <= 3600):
            raise HTTPException(status_code=422, detail="monitor_interval must be 60-3600 seconds")
        await _upsert(db, "monitor_interval", str(body.monitor_interval))

    if body.data_retention_days is not None:
        if not (1 <= body.data_retention_days <= 365):
            raise HTTPException(status_code=422, detail="data_retention_days must be 1-365")
        await _upsert(db, "data_retention_days", str(body.data_retention_days))

    await db.commit()
    return await get_app_settings(db)


@router.post("/smtp/test", response_model=SmtpTestResponse)
async def test_smtp_connection(
    body: SmtpSettingsRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send a test email using the provided (or currently saved) SMTP settings."""
    import aiosmtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    current = await get_app_settings(db)

    host = body.smtp_host or current.smtp_host
    port = body.smtp_port or current.smtp_port
    user = body.smtp_user or current.smtp_user
    password = body.smtp_password or ""
    from_addr = body.smtp_from or current.smtp_from or user
    tls = body.smtp_tls if body.smtp_tls is not None else current.smtp_tls

    if not user:
        return SmtpTestResponse(success=False, message="SMTP user not configured")
    if not password:
        return SmtpTestResponse(success=False, message="SMTP password not provided for test")

    msg = MIMEMultipart()
    msg["From"] = from_addr
    msg["To"] = user
    msg["Subject"] = "[NodeCtrl] SMTP Test"
    msg.attach(MIMEText("SMTP configuration is working correctly.", "plain"))

    smtp_kwargs: dict = dict(hostname=host, port=port, username=user, password=password)
    if port == 465:
        smtp_kwargs["use_tls"] = True
    elif tls:
        smtp_kwargs["start_tls"] = True

    try:
        await aiosmtplib.send(msg, **smtp_kwargs)
        return SmtpTestResponse(success=True, message="Test email sent successfully")
    except Exception as e:
        return SmtpTestResponse(success=False, message=str(e))
