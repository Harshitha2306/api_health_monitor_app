from datetime import timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from app.authz import admin_required
from app.extensions import db
from app.models import Alert, HealthCheck, MonitoredService, utcnow
from app.services.audit import record_audit
from app.services.metrics import dashboard_metrics, service_metrics, uptime_for_service
from app.services.monitor import perform_health_check
from app.services.validation import validate_service_payload

monitoring_api_bp = Blueprint("monitoring_api", __name__)


def api_error(code, message, status=400, details=None):
    body = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return jsonify(body), status


def iso(value):
    return value.isoformat() if value else None


def service_payload(service):
    latest = service.latest_check
    return {
        "id": service.id, "name": service.name, "description": service.description,
        "endpoint_url": service.endpoint_url, "method": service.method,
        "expected_status": service.expected_status, "interval_seconds": service.interval_seconds,
        "timeout_seconds": service.timeout_seconds,
        "response_threshold_ms": service.response_threshold_ms,
        "failure_threshold": service.failure_threshold, "environment": service.environment,
        "is_active": service.is_active, "health": service.health_status,
        "failure_streak": service.failure_streak,
        "last_status": latest.http_status if latest else None,
        "last_response_time_ms": latest.response_time_ms if latest else None,
        "last_checked_at": iso(service.last_checked_at),
        "created_at": iso(service.created_at), "updated_at": iso(service.updated_at),
    }


def check_payload(check):
    return {
        "id": check.id, "service_id": check.service_id,
        "checked_at": iso(check.checked_at), "response_time_ms": check.response_time_ms,
        "http_status": check.http_status, "is_healthy": check.is_healthy,
        "health_state": check.health_state, "error_message": check.error_message,
    }


def alert_payload(alert):
    return {
        "id": alert.id, "service_id": alert.service_id,
        "service_name": alert.service.name, "severity": alert.severity,
        "title": alert.title, "message": alert.message, "status": alert.status,
        "created_at": iso(alert.created_at), "acknowledged_at": iso(alert.acknowledged_at),
        "resolved_at": iso(alert.resolved_at), "duration_seconds": alert.duration_seconds,
    }


def find_service(service_id):
    return db.session.get(MonitoredService, service_id)


def apply_payload(service, payload):
    string_fields = ("name", "description", "endpoint_url", "method", "environment")
    integer_fields = ("expected_status", "interval_seconds", "timeout_seconds", "response_threshold_ms", "failure_threshold")
    for field in string_fields:
        if field in payload:
            value = payload[field]
            setattr(service, field, value.strip() if isinstance(value, str) else value)
    if "method" in payload:
        service.method = str(payload["method"]).upper()
    if "post_body" in payload:
        import json
        service.post_body = json.dumps(payload["post_body"]) if isinstance(payload["post_body"], (dict, list)) else payload["post_body"]
    for field in integer_fields:
        if field in payload:
            setattr(service, field, int(payload[field]))
    if "is_active" in payload:
        service.is_active = payload["is_active"] if isinstance(payload["is_active"], bool) else str(payload["is_active"]).lower() in {"1", "true", "yes"}


@monitoring_api_bp.get("/health")
def api_health():
    try:
        db.session.execute(db.select(MonitoredService.id).limit(1))
        database = "ok"
    except Exception:
        database = "error"
    return jsonify({"status": "ok" if database == "ok" else "degraded", "application": "PulseOps", "database": database})


@monitoring_api_bp.get("/services")
def api_services():
    return jsonify([service_payload(service) for service in MonitoredService.query.order_by(MonitoredService.name).all()])


@monitoring_api_bp.get("/services/<int:service_id>")
def api_service(service_id):
    service = find_service(service_id)
    if not service:
        return api_error("SERVICE_NOT_FOUND", "The requested monitored service does not exist.", 404)
    return jsonify(service_payload(service))


@monitoring_api_bp.post("/services")
@admin_required
def api_create_service():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return api_error("INVALID_JSON", "A JSON request body is required.", 400)
    errors = validate_service_payload(payload)
    if errors:
        return api_error("VALIDATION_ERROR", "Service validation failed.", 422, errors)
    service = MonitoredService()
    defaults = {
        "method": "GET", "expected_status": 200, "interval_seconds": 60,
        "timeout_seconds": 8, "response_threshold_ms": 1000,
        "failure_threshold": 3, "environment": "Production",
    }
    apply_payload(service, {**defaults, **payload})
    db.session.add(service)
    try:
        db.session.flush()
        record_audit("service_created", "service", service.id, f"Created {service.name} through the API.")
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return api_error("SERVICE_CONFLICT", "A service with this endpoint URL already exists.", 409)
    return jsonify(service_payload(service)), 201


@monitoring_api_bp.put("/services/<int:service_id>")
@admin_required
def api_update_service(service_id):
    service = find_service(service_id)
    if not service:
        return api_error("SERVICE_NOT_FOUND", "The requested monitored service does not exist.", 404)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return api_error("INVALID_JSON", "A JSON request body is required.", 400)
    errors = validate_service_payload(payload, partial=True)
    if errors:
        return api_error("VALIDATION_ERROR", "Service validation failed.", 422, errors)
    apply_payload(service, payload)
    try:
        record_audit("service_edited", "service", service.id, f"Updated {service.name} through the API.")
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return api_error("SERVICE_CONFLICT", "A service with this endpoint URL already exists.", 409)
    return jsonify(service_payload(service))


@monitoring_api_bp.delete("/services/<int:service_id>")
@admin_required
def api_delete_service(service_id):
    service = find_service(service_id)
    if not service:
        return api_error("SERVICE_NOT_FOUND", "The requested monitored service does not exist.", 404)
    record_audit("service_deleted", "service", service.id, f"Deleted {service.name} through the API.")
    db.session.delete(service)
    db.session.commit()
    return "", 204


@monitoring_api_bp.post("/services/<int:service_id>/check")
@admin_required
def api_check(service_id):
    service = find_service(service_id)
    if not service:
        return api_error("SERVICE_NOT_FOUND", "The requested monitored service does not exist.", 404)
    check = perform_health_check(service)
    record_audit("manual_check", "service", service.id, f"Triggered API check for {service.name}.")
    db.session.commit()
    return jsonify(check_payload(check))


@monitoring_api_bp.get("/services/<int:service_id>/history")
def api_history(service_id):
    if not find_service(service_id):
        return api_error("SERVICE_NOT_FOUND", "The requested monitored service does not exist.", 404)
    limit = min(max(request.args.get("limit", 100, type=int), 1), 500)
    rows = HealthCheck.query.filter_by(service_id=service_id).order_by(HealthCheck.checked_at.desc()).limit(limit).all()
    return jsonify([check_payload(row) for row in rows])


@monitoring_api_bp.get("/services/<int:service_id>/metrics")
def api_metrics(service_id):
    service = find_service(service_id)
    if not service:
        return api_error("SERVICE_NOT_FOUND", "The requested monitored service does not exist.", 404)
    return jsonify({"service_id": service.id, **service_metrics(service.id)})


@monitoring_api_bp.get("/alerts")
def api_alerts():
    query = Alert.query
    if request.args.get("status") in {"open", "acknowledged", "resolved"}:
        query = query.filter_by(status=request.args["status"])
    if request.args.get("severity") in {"warning", "critical"}:
        query = query.filter_by(severity=request.args["severity"])
    return jsonify([alert_payload(row) for row in query.order_by(Alert.created_at.desc()).limit(500).all()])


@monitoring_api_bp.get("/dashboard/summary")
def api_dashboard_summary():
    metrics = dashboard_metrics()
    rows = HealthCheck.query.filter(HealthCheck.checked_at >= utcnow() - timedelta(hours=24)).order_by(HealthCheck.checked_at.asc()).all()
    trend_rows = HealthCheck.query.filter(HealthCheck.checked_at >= utcnow() - timedelta(days=7)).all()
    distribution = {"healthy": 0, "degraded": 0, "down": 0}
    for row in rows:
        distribution[row.health_state] = distribution.get(row.health_state, 0) + 1
    uptime_trend = []
    today = utcnow().date()
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        daily_checks = [row for row in trend_rows if row.checked_at.date() == day]
        healthy = sum(1 for row in daily_checks if row.is_healthy)
        uptime_trend.append({
            "date": day.isoformat(),
            "uptime": round(healthy / len(daily_checks) * 100, 2) if daily_checks else None,
        })
    return jsonify({
        "summary": {key: value for key, value in metrics.items() if key != "latest_rows"},
        "services": [service_payload(item["service"]) | {"uptime_24h": item["uptime_24h"]} for item in metrics["latest_rows"]],
        "charts": {
            "response_time": [{"checked_at": iso(row.checked_at), "response_time_ms": row.response_time_ms, "service": row.service.name} for row in rows[-100:]],
            "distribution": distribution,
            "uptime_trend": uptime_trend,
        },
    })
