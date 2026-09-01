from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy.exc import IntegrityError

from app.authz import admin_required
from app.extensions import db
from app.models import HealthCheck, MonitoredService
from app.services.audit import record_audit
from app.services.metrics import service_metrics
from app.services.monitor import perform_health_check
from app.services.settings import get_setting
from app.services.validation import validate_service_payload

services_bp = Blueprint("services", __name__)


def _form_payload():
    return {
        "name": request.form.get("name", "").strip(),
        "description": request.form.get("description", "").strip(),
        "endpoint_url": request.form.get("endpoint_url", "").strip(),
        "method": request.form.get("method", "GET").upper(),
        "post_body": request.form.get("post_body", "").strip() or None,
        "expected_status": request.form.get("expected_status", 200),
        "interval_seconds": request.form.get("interval_seconds", 60),
        "timeout_seconds": request.form.get("timeout_seconds", 8),
        "response_threshold_ms": request.form.get("response_threshold_ms", 1000),
        "failure_threshold": request.form.get("failure_threshold", 3),
        "environment": request.form.get("environment", "Production").strip() or "Production",
    }


def _apply_payload(service, payload):
    for field in ("name", "description", "endpoint_url", "method", "post_body", "environment"):
        setattr(service, field, payload.get(field))
    for field in ("expected_status", "interval_seconds", "timeout_seconds", "response_threshold_ms", "failure_threshold"):
        setattr(service, field, int(payload[field]))


@services_bp.get("/")
@login_required
def list_services():
    services = MonitoredService.query.order_by(MonitoredService.created_at.desc()).all()
    return render_template("services/list.html", services=services)


@services_bp.route("/new", methods=["GET", "POST"])
@admin_required
def create_service():
    defaults = {
        "interval_seconds": get_setting("default_interval_seconds"),
        "timeout_seconds": get_setting("default_timeout_seconds"),
        "failure_threshold": get_setting("default_failure_threshold"),
        "response_threshold_ms": get_setting("default_response_threshold_ms"),
    }
    if request.method == "POST":
        payload = _form_payload()
        errors = validate_service_payload(payload)
        if not errors:
            service = MonitoredService()
            _apply_payload(service, payload)
            db.session.add(service)
            try:
                db.session.flush()
                record_audit("service_created", "service", service.id, f"Created monitored service {service.name}.")
                db.session.commit()
                flash("Service added successfully.", "success")
                return redirect(url_for("services.service_detail", service_id=service.id))
            except IntegrityError:
                db.session.rollback()
                errors["endpoint_url"] = "This endpoint URL is already monitored."
        for message in errors.values():
            flash(message, "danger")
        return render_template("services/form.html", service=None, values=payload, errors=errors)
    return render_template("services/form.html", service=None, values=defaults, errors={})


@services_bp.route("/<int:service_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_service(service_id):
    service = db.get_or_404(MonitoredService, service_id)
    if request.method == "POST":
        payload = _form_payload()
        errors = validate_service_payload(payload)
        duplicate = MonitoredService.query.filter(
            MonitoredService.endpoint_url == payload["endpoint_url"],
            MonitoredService.id != service.id,
        ).first()
        if duplicate:
            errors["endpoint_url"] = "This endpoint URL is already monitored."
        if not errors:
            _apply_payload(service, payload)
            record_audit("service_edited", "service", service.id, f"Edited monitored service {service.name}.")
            db.session.commit()
            flash("Service updated.", "success")
            return redirect(url_for("services.service_detail", service_id=service.id))
        for message in errors.values():
            flash(message, "danger")
        return render_template("services/form.html", service=service, values=payload, errors=errors)
    return render_template("services/form.html", service=service, values=service, errors={})


@services_bp.get("/<int:service_id>")
@login_required
def service_detail(service_id):
    service = db.get_or_404(MonitoredService, service_id)
    page = request.args.get("page", 1, type=int)
    pagination = HealthCheck.query.filter_by(service_id=service.id).order_by(
        HealthCheck.checked_at.desc()
    ).paginate(page=page, per_page=25, error_out=False)
    timeline = HealthCheck.query.filter_by(service_id=service.id).order_by(
        HealthCheck.checked_at.desc()
    ).limit(40).all()[::-1]
    return render_template(
        "services/detail.html", service=service, checks=pagination.items,
        pagination=pagination, timeline=timeline, metrics=service_metrics(service.id),
    )


@services_bp.post("/<int:service_id>/check")
@admin_required
def check_now(service_id):
    service = db.get_or_404(MonitoredService, service_id)
    check = perform_health_check(service)
    record_audit("manual_check", "service", service.id, f"Triggered a manual check for {service.name}.")
    db.session.commit()
    flash(f"Health check completed: {check.health_state.title()}.", "success")
    return redirect(request.referrer or url_for("services.service_detail", service_id=service.id))


@services_bp.post("/<int:service_id>/toggle")
@admin_required
def toggle_service(service_id):
    service = db.get_or_404(MonitoredService, service_id)
    service.is_active = not service.is_active
    action = "monitoring_resumed" if service.is_active else "monitoring_paused"
    record_audit(action, "service", service.id, f"{'Resumed' if service.is_active else 'Paused'} monitoring for {service.name}.")
    db.session.commit()
    flash("Monitoring state updated.", "success")
    return redirect(request.referrer or url_for("services.list_services"))


@services_bp.post("/<int:service_id>/delete")
@admin_required
def delete_service(service_id):
    service = db.get_or_404(MonitoredService, service_id)
    name = service.name
    record_audit("service_deleted", "service", service.id, f"Deleted monitored service {name}.")
    db.session.delete(service)
    db.session.commit()
    flash(f"{name} was deleted.", "success")
    return redirect(url_for("services.list_services"))
