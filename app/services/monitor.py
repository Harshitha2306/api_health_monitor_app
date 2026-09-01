import json
import logging
import socket
import time

import requests
from flask import current_app

from app.extensions import db
from app.models import Alert, HealthCheck, utcnow
from app.services.validation import validate_endpoint_url

logger = logging.getLogger(__name__)


def _friendly_request_error(error):
    if isinstance(error, requests.Timeout):
        return "Connection timeout"
    if isinstance(error, requests.exceptions.SSLError):
        return "SSL error"
    if isinstance(error, requests.exceptions.ConnectionError):
        message = str(error).lower()
        if "name resolution" in message or "getaddrinfo" in message:
            return "DNS resolution failure"
        if "refused" in message:
            return "Connection refused"
        return "Connection failure"
    return "Request exception"


def perform_health_check(service):
    checked_at = utcnow()
    started = time.perf_counter()
    status_code = None
    error_message = None
    transport_success = False

    validation_error = validate_endpoint_url(service.endpoint_url)
    if validation_error:
        elapsed_ms = 0.0
        error_message = f"Invalid endpoint: {validation_error}"
    else:
        try:
            request_kwargs = {
                "method": service.method,
                "url": service.endpoint_url,
                "timeout": service.timeout_seconds or current_app.config["REQUEST_TIMEOUT_SECONDS"],
                "allow_redirects": True,
            }
            if service.method == "POST" and service.post_body:
                request_kwargs["json"] = json.loads(service.post_body)
            response = requests.request(**request_kwargs)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            status_code = response.status_code
            transport_success = status_code == service.expected_status
            if not transport_success:
                error_message = f"Unexpected status code: expected HTTP {service.expected_status}, received HTTP {status_code}."
        except (requests.RequestException, socket.error) as error:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            error_message = _friendly_request_error(error)
            logger.warning("Health check failed for service %s: %s", service.id, error_message)
        except (TypeError, ValueError):
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            error_message = "Invalid endpoint request configuration"

    if transport_success and elapsed_ms > service.response_threshold_ms:
        health_state = "degraded"
    elif transport_success:
        health_state = "healthy"
    else:
        health_state = "down"

    check = HealthCheck(
        service_id=service.id, checked_at=checked_at,
        response_time_ms=elapsed_ms, http_status=status_code,
        is_healthy=transport_success, health_state=health_state,
        error_message=error_message,
    )
    db.session.add(check)
    service.last_checked_at = checked_at
    if transport_success:
        service.failure_streak = 0
        service.last_successful_check = checked_at
    else:
        service.failure_streak += 1
        service.last_failed_check = checked_at
    db.session.flush()
    update_alert_state(service, transport_success, error_message, status_code)
    db.session.commit()
    logger.info("Health check service=%s state=%s latency_ms=%s", service.id, health_state, elapsed_ms)
    return check


def update_alert_state(service, healthy, error_message=None, status_code=None):
    active_alert = (
        Alert.query.filter(
            Alert.service_id == service.id,
            Alert.status.in_(["open", "acknowledged"]),
        ).order_by(Alert.created_at.desc()).first()
    )
    if healthy:
        if active_alert:
            active_alert.status = "resolved"
            active_alert.resolved_at = utcnow()
            logger.info("Recovered service %s; alert %s resolved", service.id, active_alert.id)
        return

    threshold = service.failure_threshold or current_app.config["ALERT_FAILURE_THRESHOLD"]
    if service.failure_streak >= threshold and not active_alert:
        detail = error_message or f"Unexpected HTTP status: {status_code}"
        alert = Alert(
            service_id=service.id,
            severity="critical",
            title=f"{service.name} is down",
            message=f"{detail} Consecutive failures: {service.failure_streak}.",
        )
        db.session.add(alert)
        logger.warning("Created incident for service %s", service.id)
