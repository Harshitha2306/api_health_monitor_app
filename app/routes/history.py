import csv
import io
from datetime import datetime, time, timezone

from flask import Blueprint, Response, render_template, request
from flask_login import login_required

from app.authz import admin_required
from app.models import Alert, HealthCheck, MonitoredService
from app.services.metrics import service_metrics

history_bp = Blueprint("history", __name__)


def _filtered_checks():
    query = HealthCheck.query
    service_id = request.args.get("service_id", type=int)
    state = request.args.get("state", "").lower()
    if service_id:
        query = query.filter_by(service_id=service_id)
    if state in {"healthy", "degraded", "down"}:
        query = query.filter_by(health_state=state)
    for key, operator in (("date_from", ">="), ("date_to", "<=")):
        value = request.args.get(key)
        if value:
            try:
                parsed = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if key == "date_to":
                    parsed = datetime.combine(parsed.date(), time.max, tzinfo=timezone.utc)
                query = query.filter(HealthCheck.checked_at >= parsed if operator == ">=" else HealthCheck.checked_at <= parsed)
            except ValueError:
                pass
    return query


@history_bp.get("/")
@login_required
def index():
    page = request.args.get("page", 1, type=int)
    pagination = _filtered_checks().order_by(HealthCheck.checked_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    return render_template(
        "history/index.html", checks=pagination.items, pagination=pagination,
        services=MonitoredService.query.order_by(MonitoredService.name).all(),
    )


@history_bp.get("/export/checks.csv")
@login_required
def export_checks():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Service", "Checked At", "HTTP Status", "Response Time (ms)", "Health State", "Error"])
    for check in _filtered_checks().order_by(HealthCheck.checked_at.desc()).all():
        writer.writerow([check.service.name, check.checked_at.isoformat(), check.http_status or "", check.response_time_ms, check.health_state, check.error_message or ""])
    return _csv_response(output, "pulseops-health-checks.csv")


@history_bp.get("/export/alerts.csv")
@login_required
def export_alerts():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Service", "Severity", "Title", "Status", "Created At", "Acknowledged At", "Resolved At", "Duration Seconds"])
    for alert in Alert.query.order_by(Alert.created_at.desc()).all():
        writer.writerow([alert.service.name, alert.severity, alert.title, alert.status, alert.created_at.isoformat(), alert.acknowledged_at.isoformat() if alert.acknowledged_at else "", alert.resolved_at.isoformat() if alert.resolved_at else "", alert.duration_seconds])
    return _csv_response(output, "pulseops-alerts.csv")


@history_bp.get("/export/uptime.csv")
@login_required
def export_uptime():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Service", "24 Hour Uptime", "7 Day Uptime", "30 Day Uptime", "All Time Uptime"])
    for service in MonitoredService.query.order_by(MonitoredService.name).all():
        metrics = service_metrics(service.id)
        writer.writerow([service.name, metrics["uptime_24h"], metrics["uptime_7d"], metrics["uptime_30d"], metrics["uptime_all"]])
    return _csv_response(output, "pulseops-uptime-report.csv")


def _csv_response(output, filename):
    return Response(
        output.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
