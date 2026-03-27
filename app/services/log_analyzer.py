import re
import os
from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.log import LogHistory
from app.models.settings import AppConfig
from app.schemas.log import LogStatistics
from app.config import get_settings

SSH_FAIL_PATTERN = re.compile(
    r"(\w+\s+\d+\s+[\d:]+)\s+\S+\s+sshd\[.*?\]:\s+Failed password for .* from ([\d.]+)"
)
FAIL2BAN_BAN_PATTERN = re.compile(
    r"(\d{4}-\d{2}-\d{2} [\d:,]+)\s+fail2ban\.\w+\s+\[.*?\]:\s+NOTICE\s+\[(\S+)\] Ban ([\d.]+)"
)
FAIL2BAN_UNBAN_PATTERN = re.compile(
    r"(\d{4}-\d{2}-\d{2} [\d:,]+)\s+fail2ban\.\w+\s+\[.*?\]:\s+NOTICE\s+\[(\S+)\] Unban ([\d.]+)"
)
NGINX_ACCESS_PATTERN = re.compile(
    r'([\d.]+) - - \[([^\]]+)\] "(\w+) ([^\s]+) [^"]*" (\d+) (\d+)'
)
NGINX_ERROR_PATTERN = re.compile(
    r"(\d{4}/\d{2}/\d{2} [\d:]+) \[(\w+)\] .+?: (.+)"
)


# ──────────────────────────────────────────────
# Timestamp parsers
# ──────────────────────────────────────────────

def _parse_syslog_ts(ts_str: str) -> datetime:
    """Parse syslog timestamp like 'Feb 21 10:30:00' (no year)."""
    now = datetime.utcnow()
    try:
        dt = datetime.strptime(f"{now.year} {ts_str.strip()}", "%Y %b %d %H:%M:%S")
        # If parsed date is in the future, it belongs to the previous year
        if dt > now + timedelta(days=1):
            dt = dt.replace(year=now.year - 1)
        return dt
    except ValueError:
        return now


def _parse_nginx_access_ts(ts_str: str) -> datetime:
    """Parse nginx access log timestamp like '21/Feb/2024:10:30:00 +0000'."""
    try:
        return datetime.strptime(ts_str.strip(), "%d/%b/%Y:%H:%M:%S %z").replace(tzinfo=None)
    except ValueError:
        return datetime.utcnow()


def _parse_nginx_error_ts(ts_str: str) -> datetime:
    """Parse nginx error log timestamp like '2024/02/21 10:30:00'."""
    try:
        return datetime.strptime(ts_str.strip(), "%Y/%m/%d %H:%M:%S")
    except ValueError:
        return datetime.utcnow()


# ──────────────────────────────────────────────
# File offset tracking via AppConfig
# ──────────────────────────────────────────────

async def _get_file_state(db: AsyncSession, source_key: str) -> tuple[int, int]:
    """Return (inode, offset) for a log source, defaults to (0, 0)."""
    result = await db.execute(
        select(AppConfig).where(AppConfig.key == f"log_offset:{source_key}")
    )
    config = result.scalar_one_or_none()
    if config and config.value:
        parts = config.value.split(":")
        if len(parts) == 2:
            try:
                return int(parts[0]), int(parts[1])
            except ValueError:
                pass
    return 0, 0


async def _set_file_state(db: AsyncSession, source_key: str, inode: int, offset: int) -> None:
    """Persist (inode, offset) for a log source."""
    result = await db.execute(
        select(AppConfig).where(AppConfig.key == f"log_offset:{source_key}")
    )
    config = result.scalar_one_or_none()
    if config:
        config.value = f"{inode}:{offset}"
    else:
        db.add(AppConfig(key=f"log_offset:{source_key}", value=f"{inode}:{offset}"))


async def _read_new_lines(filepath: str, db: AsyncSession, source_key: str) -> list[str]:
    """
    Read only the lines added to *filepath* since the last call.
    Uses inode + byte offset stored in AppConfig to handle log rotation.
    Returns an empty list if the file is missing or unreadable.
    """
    if not os.path.exists(filepath):
        return []
    try:
        stat = os.stat(filepath)
        current_inode = stat.st_ino
        current_size = stat.st_size

        stored_inode, stored_offset = await _get_file_state(db, source_key)

        # File rotated or shrunk (e.g. logrotate)
        if stored_inode != current_inode or stored_offset > current_size:
            stored_offset = 0

        if stored_offset >= current_size:
            return []  # Nothing new

        with open(filepath, "r", errors="ignore") as fh:
            fh.seek(stored_offset)
            # Cap single read to 2 MB to avoid blocking
            chunk = fh.read(2 * 1024 * 1024)
            new_offset = fh.tell()

        await _set_file_state(db, source_key, current_inode, new_offset)
        return chunk.splitlines()

    except (PermissionError, OSError):
        return []


# ──────────────────────────────────────────────
# Per-format line parsers (pure, no I/O)
# ──────────────────────────────────────────────

def _parse_auth_lines(lines: list[str]) -> list[dict]:
    entries: list[dict] = []
    ip_counts: dict[str, int] = defaultdict(int)

    for line in lines:
        m = SSH_FAIL_PATTERN.search(line)
        if m:
            ts_str, ip = m.group(1), m.group(2)
            ip_counts[ip] += 1
            entries.append({
                "timestamp": _parse_syslog_ts(ts_str),
                "log_type": "bruteforce",
                "severity": "warning",
                "source": "ssh",
                "message": f"Failed SSH login from {ip}",
                "ip_address": ip,
            })

    # Upgrade severity for repeated attempts within this batch
    for entry in entries:
        ip = entry.get("ip_address")
        if ip and ip_counts[ip] >= 5:
            entry["severity"] = "critical"
            entry["message"] = (
                f"[BruteForce] Multiple failed SSH logins from {ip} "
                f"({ip_counts[ip]} attempts)"
            )

    return entries


def _parse_nginx_access_lines(lines: list[str]) -> list[dict]:
    entries: list[dict] = []
    ip_error_counts: dict[str, int] = defaultdict(int)

    for line in lines:
        m = NGINX_ACCESS_PATTERN.search(line)
        if not m:
            continue

        ip, ts_str, method, path, status_code, _ = m.groups()
        status = int(status_code)

        if 400 <= status < 500:
            severity, log_type = "warning", "client_error"
            ip_error_counts[ip] += 1
        elif status >= 500:
            severity, log_type = "error", "server_error"
        else:
            severity, log_type = "info", "access"

        entries.append({
            "timestamp": _parse_nginx_access_ts(ts_str),
            "log_type": log_type,
            "severity": severity,
            "source": "nginx",
            "message": f"{method} {path} {status_code}",
            "ip_address": ip,
        })

    for entry in entries:
        ip = entry.get("ip_address")
        if ip and ip_error_counts[ip] >= 20:
            entry["log_type"] = "bruteforce"
            entry["severity"] = "critical"

    return entries


def _parse_fail2ban_lines(lines: list[str]) -> list[dict]:
    entries: list[dict] = []

    for line in lines:
        m = FAIL2BAN_BAN_PATTERN.search(line)
        if m:
            ts_str, jail, ip = m.group(1), m.group(2), m.group(3)
            try:
                ts = datetime.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                ts = datetime.utcnow()
            entries.append({
                "timestamp": ts,
                "log_type": "bruteforce",
                "severity": "critical",
                "source": "fail2ban",
                "message": f"[fail2ban] Banned {ip} (jail: {jail})",
                "ip_address": ip,
            })
            continue

        m = FAIL2BAN_UNBAN_PATTERN.search(line)
        if m:
            ts_str, jail, ip = m.group(1), m.group(2), m.group(3)
            try:
                ts = datetime.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                ts = datetime.utcnow()
            entries.append({
                "timestamp": ts,
                "log_type": "info",
                "severity": "info",
                "source": "fail2ban",
                "message": f"[fail2ban] Unbanned {ip} (jail: {jail})",
                "ip_address": ip,
            })

    return entries


def _parse_nginx_error_lines(lines: list[str]) -> list[dict]:
    entries: list[dict] = []

    for line in lines:
        m = NGINX_ERROR_PATTERN.search(line)
        if not m:
            continue

        ts_str, level, message = m.groups()
        severity = "error" if level in ("error", "crit", "alert", "emerg") else "warning"
        entries.append({
            "timestamp": _parse_nginx_error_ts(ts_str),
            "log_type": "error",
            "severity": severity,
            "source": "nginx-error",
            "message": message[:500],
        })

    return entries


# ──────────────────────────────────────────────
# Main collection entry point
# ──────────────────────────────────────────────

async def collect_and_save_logs(db: AsyncSession) -> int:
    settings = get_settings()

    sources = [
        ("auth_log",      settings.auth_log,          _parse_auth_lines),
        ("nginx_access",  settings.nginx_access_log,  _parse_nginx_access_lines),
        ("nginx_error",   settings.nginx_error_log,   _parse_nginx_error_lines),
        ("fail2ban",      settings.fail2ban_log,       _parse_fail2ban_lines),
    ]

    saved = 0
    for source_key, filepath, parser_fn in sources:
        lines = await _read_new_lines(filepath, db, source_key)
        if not lines:
            continue

        entries = parser_fn(lines)
        for entry in entries:
            db.add(LogHistory(
                timestamp=entry["timestamp"],
                log_type=entry["log_type"],
                severity=entry["severity"],
                source=entry["source"],
                message=entry["message"],
                ip_address=entry.get("ip_address"),
            ))
            saved += 1

    if saved > 0:
        await db.commit()

    return saved


# ──────────────────────────────────────────────
# Statistics helper (used by router)
# ──────────────────────────────────────────────

async def get_log_statistics(db: AsyncSession, hours: int = 24) -> LogStatistics:
    since = datetime.utcnow() - timedelta(hours=hours)

    result_type = await db.execute(
        select(LogHistory.log_type, func.count(LogHistory.id))
        .where(LogHistory.timestamp >= since)
        .group_by(LogHistory.log_type)
    )
    by_type = {row[0]: row[1] for row in result_type.all()}

    result_sev = await db.execute(
        select(LogHistory.severity, func.count(LogHistory.id))
        .where(LogHistory.timestamp >= since)
        .group_by(LogHistory.severity)
    )
    by_severity = {row[0]: row[1] for row in result_sev.all()}

    total = sum(by_type.values())

    return LogStatistics(
        total=total,
        bruteforce_attempts=by_type.get("bruteforce", 0),
        errors=by_type.get("error", 0) + by_type.get("server_error", 0),
        by_type=by_type,
        by_severity=by_severity,
    )
