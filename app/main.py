import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, delete

from app.config import get_settings
from app.database import init_db, AsyncSessionLocal
from app.routers import system, services, logs, alerts, dashboard, settings as settings_router
from app.routers import auth as auth_router
from app.auth import get_current_user
from app.services.monitor import save_monitoring_snapshot
from app.services.log_analyzer import collect_and_save_logs
from app.services.notification import check_alerts
from app.models.monitoring import MonitoringHistory
from app.models.log import LogHistory
from app.models.alert import AlertSetting

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

# Default alert thresholds seeded on first start
_DEFAULT_ALERT_SETTINGS = [
    {"metric_type": "cpu",    "threshold": 80.0, "enabled": True},
    {"metric_type": "memory", "threshold": 85.0, "enabled": True},
    {"metric_type": "disk",   "threshold": 90.0, "enabled": True},
]


# ──────────────────────────────────────────────
# Scheduled tasks
# ──────────────────────────────────────────────

async def scheduled_monitoring_task():
    async with AsyncSessionLocal() as db:
        try:
            await save_monitoring_snapshot(db)
            logger.debug("Monitoring snapshot saved")
        except Exception as e:
            logger.error("Monitoring task failed: %s", e)


async def scheduled_log_task():
    async with AsyncSessionLocal() as db:
        try:
            count = await collect_and_save_logs(db)
            if count > 0:
                logger.debug("Saved %d log entries", count)
        except Exception as e:
            logger.error("Log collection task failed: %s", e)


async def scheduled_alert_task():
    async with AsyncSessionLocal() as db:
        try:
            triggered = await check_alerts(db)
            for alert in triggered:
                logger.warning("Alert triggered: %s", alert["message"])
        except Exception as e:
            logger.error("Alert check task failed: %s", e)


async def scheduled_cleanup_task():
    """Delete monitoring and log records older than the configured retention period."""
    settings = get_settings()
    async with AsyncSessionLocal() as db:
        try:
            monitor_cutoff = datetime.utcnow() - timedelta(days=settings.data_retention_days)
            result = await db.execute(
                delete(MonitoringHistory).where(MonitoringHistory.timestamp < monitor_cutoff)
            )
            deleted_m = result.rowcount

            # Keep logs for 3× the monitoring retention period (capped at 90 days)
            log_days = min(settings.data_retention_days * 3, 90)
            log_cutoff = datetime.utcnow() - timedelta(days=log_days)
            result = await db.execute(
                delete(LogHistory).where(LogHistory.timestamp < log_cutoff)
            )
            deleted_l = result.rowcount

            await db.commit()
            if deleted_m or deleted_l:
                logger.info(
                    "Cleanup: removed %d monitoring rows and %d log rows",
                    deleted_m, deleted_l,
                )
        except Exception as e:
            logger.error("Cleanup task failed: %s", e)


# ──────────────────────────────────────────────
# Startup helpers
# ──────────────────────────────────────────────

async def seed_default_alert_settings() -> None:
    """Insert default alert settings if the table is empty."""
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(AlertSetting).limit(1))
            if result.scalar_one_or_none() is not None:
                return  # Already seeded

            for defaults in _DEFAULT_ALERT_SETTINGS:
                db.add(AlertSetting(**defaults))
            await db.commit()
            logger.info("Seeded default alert settings")
        except Exception as e:
            logger.error("Failed to seed alert settings: %s", e)


# ──────────────────────────────────────────────
# App factory
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    await init_db()
    logger.info("Database initialized")

    await seed_default_alert_settings()

    interval = settings.monitor_interval
    now = datetime.utcnow()

    scheduler.add_job(
        scheduled_monitoring_task,
        "interval",
        seconds=interval,
        id="monitoring",
        name="System Monitoring",
        next_run_time=now,
    )
    scheduler.add_job(
        scheduled_log_task,
        "interval",
        seconds=interval,
        id="log_collection",
        name="Log Collection",
        next_run_time=now,
    )
    scheduler.add_job(
        scheduled_alert_task,
        "interval",
        seconds=interval,
        id="alert_check",
        name="Alert Check",
        next_run_time=now,
    )
    # Cleanup runs once a day at 03:00
    scheduler.add_job(
        scheduled_cleanup_task,
        "cron",
        hour=3,
        minute=0,
        id="cleanup",
        name="Data Cleanup",
    )

    scheduler.start()
    logger.info("Background scheduler started (interval: %ds)", interval)

    yield

    scheduler.shutdown()
    logger.info("Scheduler stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="HomeServer Dashboard API",
        description="HomeServer Dashboard API",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Auth router — public (no auth required)
    app.include_router(auth_router.router)

    # All other routers require authentication
    _auth_dep = [Depends(get_current_user)]
    app.include_router(system.router, dependencies=_auth_dep)
    app.include_router(services.router, dependencies=_auth_dep)
    app.include_router(logs.router, dependencies=_auth_dep)
    app.include_router(alerts.router, dependencies=_auth_dep)
    app.include_router(dashboard.router, dependencies=_auth_dep)
    app.include_router(settings_router.router, dependencies=_auth_dep)

    @app.get("/api/health")
    async def health_check():
        return {"status": "ok", "service": "nodectrl-api"}

    return app


app = create_app()
