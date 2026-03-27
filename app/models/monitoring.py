from datetime import datetime
from sqlalchemy import Integer, Float, BigInteger, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class MonitoringHistory(Base):
    __tablename__ = "monitoring_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    cpu_usage: Mapped[float] = mapped_column(Float)
    cpu_per_core: Mapped[dict] = mapped_column(JSON, nullable=True)
    memory_total: Mapped[int] = mapped_column(BigInteger)
    memory_used: Mapped[int] = mapped_column(BigInteger)
    memory_percent: Mapped[float] = mapped_column(Float)
    swap_used: Mapped[int] = mapped_column(BigInteger, default=0)
    disk_usage: Mapped[dict] = mapped_column(JSON, nullable=True)
    network_rx_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    network_tx_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
