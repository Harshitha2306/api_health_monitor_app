import sqlite3
import time

from flask import Blueprint, current_app, render_template
from flask_login import login_required

from app import APPLICATION_STARTED_AT
from app.models import Alert, MonitoredService
from app.services.metrics import dashboard_metrics
from app.services.scheduler import scheduler, scheduler_state
from app.services.settings import get_setting

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("/")
@login_required
def index():
    metrics = dashboard_metrics()
    recent_alerts = Alert.query.order_by(Alert.created_at.desc()).limit(6).all()
    database_ok = True
    try:
        MonitoredService.query.limit(1).all()
    except Exception:
        database_ok = False
    engine_health = {
        "scheduler_state": "Running" if scheduler.running else ("Disabled" if not current_app.config.get("SCHEDULER_ENABLED") else "Stopped"),
        "last_cycle": scheduler_state["last_cycle"],
        "active_monitors": metrics["active_services"],
        "database_status": "Connected" if database_ok else "Unavailable",
        "application_uptime": int(time.time() - APPLICATION_STARTED_AT),
    }
    return render_template(
        "dashboard/index.html", metrics=metrics, recent_alerts=recent_alerts,
        engine_health=engine_health, refresh_seconds=get_setting("dashboard_refresh_seconds"),
    )
