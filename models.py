"""SQLAlchemy models for the Trade Signal Bot.

The `Config` table stores API credentials and channel configuration.
The `Signal` table optionally stores a history of forwarded signals.

When using SQLite, a single process/thread must write to the database
to avoid locking issues.  See `gunicorn.conf.py` for details.
"""

from __future__ import annotations
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, DateTime
from datetime import datetime


class Base(DeclarativeBase):
    """Base class for declarative models."""
    pass


# Initialise SQLAlchemy with our custom base class.
db = SQLAlchemy(model_class=Base)


class Config(db.Model):
    """Configuration for the signal bot.

    Only a single row is expected in this table.  It contains API
    credentials, the name of the Telethon session file, the JSON
    representation of source channels, and the destination channels.
    """

    __tablename__ = "config"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    api_id: Mapped[str | None] = mapped_column(String(32))
    api_hash: Mapped[str | None] = mapped_column(String(128))
    session_name: Mapped[str] = mapped_column(String(64), default="signal_bot")
    from_channels: Mapped[str | None] = mapped_column(Text)  # JSON array of sources
    to_channels: Mapped[str | None] = mapped_column(Text)  # JSON array of destinations


class Signal(db.Model):
    """Minimalistic history of forwarded signals.

    This table is optional and can be disabled if persistent
    storage is not required.  Only a subset of the parsed data is
    stored; adjust the model to your needs.
    """

    __tablename__ = "signal"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32))
    position: Mapped[str] = mapped_column(String(32))
    entry: Mapped[str] = mapped_column(String(32))
    sl: Mapped[str] = mapped_column(String(32))
    rr: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tps: Mapped[str] = mapped_column(Text)  # JSON list of TP strings
    source_chat_id: Mapped[str | None] = mapped_column(String(64))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
