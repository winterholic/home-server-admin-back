from datetime import datetime
from sqlalchemy import Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class LogHistory(Base):
    __tablename__ = "log_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    log_type: Mapped[str] = mapped_column(String(50), index=True)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    source: Mapped[str] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    count: Mapped[int] = mapped_column(Integer, default=1)
