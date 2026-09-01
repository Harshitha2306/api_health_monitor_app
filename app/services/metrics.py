from datetime import timedelta

from sqlalchemy import case, func

from app.extensions import db
from app.models import Alert, HealthCheck, MonitoredService, utcnow


def uptime_for_service(service_id, since=None):
    query = db.session.query(
        func.count(HealthCheck.id),
        func.sum(case((HealthCheck.is_healthy.is_(True), 1), else_=0)),
    ).filter(HealthCheck.service_id == service_id)
    if since:
        query = query.filter(HealthCheck.checked_at >= since)
    total, healthy = query.one()
    return None if not total else round((int(healthy or 0) / total) * 100, 2)


def latency_metrics(service_id, since=None):
    query = db.session.query(
        func.avg(HealthCheck.response_time_ms),
        func.min(HealthCheck.response_time_ms),
        func.max(HealthCheck.response_time_ms),
    ).filter(HealthCheck.service_id == service_id)
    if since:
        query = query.filter(HealthCheck.checked_at >= since)
    average, minimum, maximum = query.one()
    return {
        "average": round(float(average), 2) if average is not None else None,
        "minimum": round(float(minimum), 2) if minimum is not None else None,
        "maximum": round(float(maximum), 2) if maximum is not None else None,
    }


def service_metrics(service_id):
    now = utcnow()
    result = {
        "uptime_24h": uptime_for_service(service_id, now - timedelta(hours=24)),
        "uptime_7d": uptime_for_service(service_id, now - timedelta(days=7)),
        "uptime_30d": uptime_for_service(service_id, now - timedelta(days=30)),
        "uptime_all": uptime_for_service(service_id),
    }
    result.update(latency_metrics(service_id))
    return result


def dashboard_metrics():
    now = utcnow()
    services = MonitoredService.query.order_by(MonitoredService.name.asc()).all()
    counts = {"healthy": 0, "degraded": 0, "down": 0, "pending": 0, "paused": 0}
    latest_rows = []
    for service in services:
        counts[service.health_status] += 1
        latest_rows.append({
            "service": service,
            "check": service.latest_check,
            "uptime_24h": uptime_for_service(service.id, now - timedelta(hours=24)),
        })
    avg_response = db.session.query(func.avg(HealthCheck.response_time_ms)).filter(
        HealthCheck.checked_at >= now - timedelta(hours=24)
    ).scalar()
    total_24h = HealthCheck.query.filter(HealthCheck.checked_at >= now - timedelta(hours=24)).count()
    healthy_24h = HealthCheck.query.filter(
        HealthCheck.checked_at >= now - timedelta(hours=24),
        HealthCheck.is_healthy.is_(True),
    ).count()
    return {
        "total_services": len(services),
        "active_services": sum(1 for service in services if service.is_active),
        "healthy_services": counts["healthy"],
        "degraded_services": counts["degraded"],
        "down_services": counts["down"],
        "pending_services": counts["pending"],
        "paused_services": counts["paused"],
        "open_alerts": Alert.query.filter(Alert.status.in_(["open", "acknowledged"])).count(),
        "avg_response": round(float(avg_response), 1) if avg_response is not None else None,
        "uptime_pct": round(healthy_24h / total_24h * 100, 2) if total_24h else None,
        "latest_rows": latest_rows,
    }
