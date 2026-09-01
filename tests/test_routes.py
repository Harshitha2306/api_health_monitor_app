from unittest.mock import Mock, patch

import requests

from app.extensions import db
from app.models import Alert, HealthCheck, MonitoredService, User, utcnow
from app.services.metrics import uptime_for_service
from app.services.monitor import perform_health_check


def service_values(**overrides):
    values = {
        "name": "Example API", "endpoint_url": "https://example.com/health",
        "method": "GET", "expected_status": 200, "interval_seconds": 60,
        "timeout_seconds": 5, "response_threshold_ms": 1000,
        "failure_threshold": 2, "environment": "Test",
    }
    values.update(overrides)
    return values


def test_dashboard_loads_when_database_is_empty(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Monitoring Overview" in response.data
    assert b"No monitored services configured" in response.data


def test_service_create_edit_and_delete(client, app):
    response = client.post("/services/new", data=service_values(), follow_redirects=True)
    assert response.status_code == 200
    assert b"Example API" in response.data
    with app.app_context():
        service_id = MonitoredService.query.one().id
    response = client.post(f"/services/{service_id}/edit", data=service_values(name="Renamed API", interval_seconds=120), follow_redirects=True)
    assert b"Service updated" in response.data
    with app.app_context():
        assert db.session.get(MonitoredService, service_id).interval_seconds == 120
    assert client.post(f"/services/{service_id}/delete", follow_redirects=True).status_code == 200
    with app.app_context():
        assert db.session.get(MonitoredService, service_id) is None


def test_api_crud_and_validation(client):
    assert client.get("/api/v1/services").get_json() == []
    invalid = client.post("/api/v1/services", json={"name": "Unsafe", "endpoint_url": "file:///etc/passwd"})
    assert invalid.status_code == 422
    assert invalid.get_json()["error"]["code"] == "VALIDATION_ERROR"
    created = client.post("/api/v1/services", json=service_values())
    assert created.status_code == 201
    service_id = created.get_json()["id"]
    assert client.get(f"/api/v1/services/{service_id}").status_code == 200
    assert client.put(f"/api/v1/services/{service_id}", json={"name": "Updated"}).get_json()["name"] == "Updated"
    assert client.delete(f"/api/v1/services/{service_id}").status_code == 204
    assert client.get(f"/api/v1/services/{service_id}").status_code == 404


def test_successful_and_failed_health_checks(app):
    with app.app_context():
        service = MonitoredService(**service_values())
        db.session.add(service)
        db.session.commit()
        with patch("app.services.monitor.requests.request", return_value=Mock(status_code=200)):
            check = perform_health_check(service)
        assert check.is_healthy is True and check.health_state == "healthy"
        with patch("app.services.monitor.requests.request", side_effect=requests.Timeout()):
            check = perform_health_check(service)
        assert check.is_healthy is False
        assert check.error_message == "Connection timeout"
        assert HealthCheck.query.count() == 2


def test_slow_success_is_degraded_but_available(app):
    with app.app_context():
        service = MonitoredService(**service_values(response_threshold_ms=1))
        db.session.add(service)
        db.session.commit()
        with patch("app.services.monitor.time.perf_counter", side_effect=[10.0, 10.01]):
            with patch("app.services.monitor.requests.request", return_value=Mock(status_code=200)):
                check = perform_health_check(service)
        assert check.is_healthy is True
        assert check.health_state == "degraded"
        assert check.response_time_ms == 10.0


def test_alert_threshold_duplicate_prevention_and_recovery(app):
    with app.app_context():
        service = MonitoredService(**service_values(failure_threshold=2))
        db.session.add(service)
        db.session.commit()
        with patch("app.services.monitor.requests.request", side_effect=requests.ConnectionError("refused")):
            perform_health_check(service)
            assert Alert.query.count() == 0
            perform_health_check(service)
            assert Alert.query.count() == 1
            perform_health_check(service)
            assert Alert.query.count() == 1
        with patch("app.services.monitor.requests.request", return_value=Mock(status_code=200)):
            perform_health_check(service)
        assert Alert.query.one().status == "resolved"
        assert service.failure_streak == 0


def test_uptime_calculation_uses_recorded_checks(app):
    with app.app_context():
        service = MonitoredService(**service_values())
        db.session.add(service)
        db.session.flush()
        db.session.add_all([
            HealthCheck(service_id=service.id, is_healthy=True, health_state="healthy"),
            HealthCheck(service_id=service.id, is_healthy=True, health_state="degraded"),
            HealthCheck(service_id=service.id, is_healthy=False, health_state="down"),
        ])
        db.session.commit()
        assert uptime_for_service(service.id) == 66.67


def test_authentication_and_role_permissions(client, app):
    with app.app_context():
        admin = User(username="admin", email="admin@test.local", role="admin")
        admin.set_password("strong-password")
        viewer = User(username="viewer", email="viewer@test.local", role="viewer")
        viewer.set_password("strong-password")
        db.session.add_all([admin, viewer])
        db.session.commit()
    app.config["LOGIN_DISABLED"] = False
    assert client.get("/").status_code == 302
    client.post("/login", data={"identity": "viewer", "password": "strong-password"})
    assert client.get("/").status_code == 200
    assert client.post("/services/new", data=service_values()).status_code == 403
    client.post("/logout")
    client.post("/login", data={"identity": "admin", "password": "strong-password"})
    assert client.post("/services/new", data=service_values()).status_code == 302


def test_exports_and_health_api(client, app):
    with app.app_context():
        service = MonitoredService(**service_values())
        db.session.add(service)
        db.session.flush()
        db.session.add(HealthCheck(service_id=service.id, is_healthy=True, health_state="healthy"))
        db.session.commit()
    response = client.get("/history/export/checks.csv")
    assert response.status_code == 200
    assert b"Response Time (ms)" in response.data
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.get_json()["application"] == "PulseOps"


def test_navigation_pages_and_templates_render(client, app):
    with app.app_context():
        service = MonitoredService(**service_values())
        db.session.add(service)
        db.session.flush()
        alert = Alert(
            service_id=service.id, severity="critical", title="Test incident",
            message="A test incident used to validate templates.",
        )
        db.session.add(alert)
        db.session.commit()
        service_id, alert_id = service.id, alert.id
    pages = [
        "/services/", f"/services/{service_id}", f"/services/{service_id}/edit",
        "/alerts/", f"/alerts/{alert_id}", "/history/", "/api-docs",
        "/audit-log", "/settings",
    ]
    for path in pages:
        response = client.get(path)
        assert response.status_code == 200, path


def test_scheduler_checks_only_due_active_services(app):
    from app.services.scheduler import run_monitoring_cycle

    with app.app_context():
        due = MonitoredService(**service_values(name="Due", endpoint_url="https://due.example.com"))
        recent = MonitoredService(**service_values(name="Recent", endpoint_url="https://recent.example.com"))
        recent.last_checked_at = utcnow()
        paused = MonitoredService(**service_values(name="Paused", endpoint_url="https://paused.example.com"))
        paused.is_active = False
        db.session.add_all([due, recent, paused])
        db.session.commit()
        with patch("app.services.scheduler.perform_health_check") as probe:
            run_monitoring_cycle(app)
        probe.assert_called_once()
        assert probe.call_args.args[0].id == due.id
