from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.authz import admin_required
from app.extensions import db
from app.models import Alert, MonitoredService, utcnow
from app.services.audit import record_audit

alerts_bp = Blueprint("alerts", __name__)


@alerts_bp.get("/")
@login_required
def list_alerts():
    query = Alert.query
    status = request.args.get("status", "").lower()
    severity = request.args.get("severity", "").lower()
    service_id = request.args.get("service_id", type=int)
    search = request.args.get("q", "").strip()
    if status in {"open", "acknowledged", "resolved"}:
        query = query.filter_by(status=status)
    if severity in {"warning", "critical"}:
        query = query.filter_by(severity=severity)
    if service_id:
        query = query.filter_by(service_id=service_id)
    if search:
        query = query.filter((Alert.title.ilike(f"%{search}%")) | (Alert.message.ilike(f"%{search}%")))
    page = request.args.get("page", 1, type=int)
    pagination = query.order_by(Alert.created_at.desc()).paginate(page=page, per_page=25, error_out=False)
    summary = {key: Alert.query.filter_by(status=key).count() for key in ("open", "acknowledged", "resolved")}
    summary.update({key: Alert.query.filter_by(severity=key).count() for key in ("critical", "warning")})
    return render_template(
        "alerts/list.html", alerts=pagination.items, pagination=pagination,
        summary=summary, services=MonitoredService.query.order_by(MonitoredService.name).all(),
    )


@alerts_bp.get("/<int:alert_id>")
@login_required
def alert_detail(alert_id):
    return render_template("alerts/detail.html", alert=db.get_or_404(Alert, alert_id))


@alerts_bp.post("/<int:alert_id>/acknowledge")
@admin_required
def acknowledge_alert(alert_id):
    alert = db.get_or_404(Alert, alert_id)
    if alert.status == "open":
        alert.status = "acknowledged"
        alert.acknowledged_at = utcnow()
        record_audit("alert_acknowledged", "alert", alert.id, f"Acknowledged alert {alert.title}.")
        db.session.commit()
    flash("Alert acknowledged.", "success")
    return redirect(request.referrer or url_for("alerts.list_alerts"))


@alerts_bp.post("/<int:alert_id>/resolve")
@admin_required
def resolve_alert(alert_id):
    alert = db.get_or_404(Alert, alert_id)
    if alert.status != "resolved":
        alert.status = "resolved"
        alert.resolved_at = utcnow()
        record_audit("alert_resolved", "alert", alert.id, f"Resolved alert {alert.title}.")
        db.session.commit()
    flash("Alert resolved.", "success")
    return redirect(request.referrer or url_for("alerts.list_alerts"))
