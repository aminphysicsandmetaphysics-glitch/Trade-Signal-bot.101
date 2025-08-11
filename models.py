from __future__ import annotations
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Config(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    api_id = db.Column(db.String(32), nullable=True)
    api_hash = db.Column(db.String(128), nullable=True)
    session_name = db.Column(db.String(64), default="signal_bot")
    from_channels = db.Column(db.Text, default="[]")  # JSON list: ["hfjfdjjdd", 1467736193, ...]
    to_channels = db.Column(db.Text, default="[]")    # JSON list
    skip_rr = db.Column(db.Text, default="[]")        # JSON list of ints
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Signal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source_chat_id = db.Column(db.String(64))
    raw = db.Column(db.Text)
    formatted = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)