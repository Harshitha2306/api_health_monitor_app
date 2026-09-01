from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import Index
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="viewer")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    audit_logs = db.relationship("AuditLog", backref="user", lazy="dynamic")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role.lower() == "admin"


class MonitoredService(db.Model):
    __tablename__ = "monitored_services"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(1000), nullable=True)
    endpoint_url = db.Column(db.String(500), nullable=False, unique=True)
    method = db.Column(db.String(10), nullable=False, default="GET")
    post_body = db.Column(db.Text, nullable=True)
    expected_status = db.Column(db.Integer, nullable=False, default=200)
    interval_seconds = db.Column(db.Integer, nullable=False, default=60)
    timeout_seconds = db.Column(db.Integer, nullable=False, default=8)
    response_threshold_ms = db.Column(db.Integer, nullable=False, default=1000)
    failure_threshold = db.Column(db.Integer, nullable=False, default=3)
    environment = db.Column(db.String(60), nullable=False, default="Production")
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    failure_streak = db.Column(db.Integer, nullable=False, default=0)
    last_checked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    last_successful_check = db.Column(db.DateTime(timezone=True), nullable=True)
    last_failed_check = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    checks = db.relationship("HealthCheck", backref="service", lazy="dynamic", cascade="all, delete-orphan")
    alerts = db.relationship("Alert", backref="service", lazy="dynamic", cascade="all, delete-orphan")

    @property
    def latest_check(self):
        return self.checks.order_by(HealthCheck.checked_at.desc()).first()

    @property
    def health_status(self):
        if not self.is_active:
            return "paused"
        latest = self.latest_check
        return latest.health_state if latest else "pending"


class HealthCheck(db.Model):
    __tablename__ = "health_checks"
    __table_args__ = (Index("ix_health_service_checked", "service_id", "checked_at"),)
    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.Integer, db.ForeignKey("monitored_services.id"), nullable=False, index=True)
    checked_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    response_time_ms = db.Column(db.Float, nullable=True)
    http_status = db.Column(db.Integer, nullable=True)
    is_healthy = db.Column(db.Boolean, nullable=False, default=False)
    health_state = db.Column(db.String(20), nullable=False, default="down", index=True)
    error_message = db.Column(db.String(1000), nullable=True)


class Alert(db.Model):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alert_status_created", "status", "created_at"),)
    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.Integer, db.ForeignKey("monitored_services.id"), nullable=False, index=True)
    severity = db.Column(db.String(20), nullable=False, default="critical", index=True)
    title = db.Column(db.String(180), nullable=False)
    message = db.Column(db.String(1000), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    acknowledged_at = db.Column(db.DateTime(timezone=True), nullable=True)
    resolved_at = db.Column(db.DateTime(timezone=True), nullable=True)

    @property
    def duration_seconds(self):
        end, start = self.resolved_at or utcnow(), self.created_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return max(0, int((end - start).total_seconds()))


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    entity_type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer, nullable=True)
    description = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)


class ApplicationSetting(db.Model):
    __tablename__ = "application_settings"
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.String(500), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
