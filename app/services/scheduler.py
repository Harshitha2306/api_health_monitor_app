import logging
import os
from datetime import timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app.models import MonitoredService, utcnow
from app.services.maintenance import delete_expired_health_checks
from app.services.monitor import perform_health_check

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
scheduler_state = {"last_cycle": None, "started_at": None}


def run_monitoring_cycle(app):
    with app.app_context():
        now = utcnow()
        scheduler_state["last_cycle"] = now
        for service in MonitoredService.query.filter_by(is_active=True).all():
            last_checked = service.last_checked_at
            if last_checked and last_checked.tzinfo is None:
                last_checked = last_checked.replace(tzinfo=timezone.utc)
            seconds_since_check = (now - last_checked).total_seconds() if last_checked else None
            if seconds_since_check is None or seconds_since_check >= service.interval_seconds:
                try:
                    perform_health_check(service)
                except Exception:
                    logger.exception("Scheduled check failed for service %s", service.id)


def start_scheduler(app):
    if scheduler.running or not app.config.get("SCHEDULER_ENABLED", True) or app.testing:
        return
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return
    tick = max(5, int(app.config.get("SCHEDULER_TICK_SECONDS", 10)))
    scheduler.add_job(
        run_monitoring_cycle, "interval", seconds=tick, args=[app],
        id="monitoring-cycle", replace_existing=True, max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _run_cleanup, "cron", hour=3, args=[app], id="history-cleanup",
        replace_existing=True, max_instances=1,
    )
    scheduler.start()
    scheduler_state["started_at"] = utcnow()
    logger.info("PulseOps scheduler started with a %s-second tick", tick)


def _run_cleanup(app):
    with app.app_context():
        deleted = delete_expired_health_checks()
        logger.info("Health history cleanup deleted %s expired records", deleted)
