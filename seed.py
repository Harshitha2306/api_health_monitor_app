import argparse
import getpass
import os
import sys
from datetime import timedelta

from app import create_app
from app.extensions import db
from app.models import Alert, HealthCheck, MonitoredService, User, utcnow


SAMPLE_SERVICES = [
    {
        "name": "GitHub API", "description": "Public source-control platform API.",
        "endpoint_url": "https://api.github.com", "environment": "External API",
        "expected_status": 200, "interval_seconds": 60,
    },
    {
        "name": "JSONPlaceholder", "description": "Public REST API used for development validation.",
        "endpoint_url": "https://jsonplaceholder.typicode.com/posts/1",
        "environment": "Development", "expected_status": 200, "interval_seconds": 90,
    },
    {
        "name": "HTTPBin Health", "description": "Public HTTP behavior test endpoint.",
        "endpoint_url": "https://httpbin.org/status/200", "environment": "External API",
        "expected_status": 200, "interval_seconds": 120,
    },
    {
        "name": "Open-Meteo Forecast", "description": "Global weather forecast API.",
        "endpoint_url": "https://api.open-meteo.com/v1/forecast?latitude=28.61&longitude=77.21&current=temperature_2m",
        "environment": "Production", "expected_status": 200, "interval_seconds": 180,
    },
    {
        "name": "Dog CEO API", "description": "Public dog image API used as an availability probe.",
        "endpoint_url": "https://dog.ceo/api/breeds/image/random", "environment": "External API",
        "expected_status": 200, "interval_seconds": 150,
    },
    {
        "name": "Flask Repository", "description": "GitHub API health for the Flask repository.",
        "endpoint_url": "https://api.github.com/repos/pallets/flask", "environment": "Production",
        "expected_status": 200, "interval_seconds": 180,
    },
    {
        "name": "JSONPlaceholder Users", "description": "Secondary JSONPlaceholder collection endpoint.",
        "endpoint_url": "https://jsonplaceholder.typicode.com/users", "environment": "Staging",
        "expected_status": 200, "interval_seconds": 120,
    },
    {
        "name": "HTTPBin Latency", "description": "Delayed response endpoint for latency monitoring.",
        "endpoint_url": "https://httpbin.org/delay/1", "environment": "Staging",
        "expected_status": 200, "interval_seconds": 180, "response_threshold_ms": 750,
    },
]


def seed_services():
    created = 0
    for values in SAMPLE_SERVICES:
        if not MonitoredService.query.filter_by(endpoint_url=values["endpoint_url"]).first():
            db.session.add(MonitoredService(**values))
            created += 1
    db.session.commit()
    print(f"Created {created} sample service(s).")


def seed_history():
    """Create deterministic demo observations without duplicating an existing dataset."""
    services = MonitoredService.query.order_by(MonitoredService.id).all()
    if not services:
        raise SystemExit("Seed services before creating demo history.")
    now = utcnow()
    created = 0
    for service_index, service in enumerate(services):
        if service.checks.count() >= 10:
            continue
        baseline = 115 + service_index * 47
        for slot in range(56, 0, -1):
            checked_at = now - timedelta(hours=slot * 3)
            cycle = (slot + service_index * 3) % 19
            is_down = cycle == 0
            is_degraded = cycle in {6, 12}
            latency = baseline + ((slot * 31 + service_index * 17) % 180)
            if is_degraded:
                latency = max(latency, service.response_threshold_ms + 140)
            check = HealthCheck(
                service_id=service.id,
                checked_at=checked_at,
                response_time_ms=None if is_down else float(latency),
                http_status=503 if is_down else 200,
                is_healthy=not is_down,
                health_state="down" if is_down else ("degraded" if is_degraded else "healthy"),
                error_message="Upstream service unavailable" if is_down else None,
            )
            db.session.add(check)
            created += 1
    if created and not Alert.query.filter(Alert.title.like("Demo incident:%")).first():
        service = services[2 if len(services) > 2 else 0]
        db.session.add(Alert(
            service_id=service.id,
            severity="critical",
            title=f"Demo incident: {service.name}",
            message="The endpoint briefly returned an unexpected status and recovered.",
            status="resolved",
            created_at=now - timedelta(days=2, hours=4),
            resolved_at=now - timedelta(days=2, hours=3, minutes=42),
        ))
    db.session.commit()
    print(f"Created {created} demo health check(s).")


def seed_admin(username, email):
    if User.query.filter((User.username == username) | (User.email == email)).first():
        print("Admin seed skipped: that username or email already exists.")
        return
    password = os.getenv("PULSEOPS_ADMIN_PASSWORD")
    if not password and sys.stdin.isatty():
        password = getpass.getpass("New admin password: ")
        confirmation = getpass.getpass("Confirm admin password: ")
        if password != confirmation:
            raise SystemExit("Passwords do not match.")
    if not password or len(password) < 10:
        raise SystemExit("Set PULSEOPS_ADMIN_PASSWORD to at least 10 characters or run interactively.")
    user = User(username=username, email=email.lower(), role="admin")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    print(f"Created administrator '{username}'.")


def main():
    parser = argparse.ArgumentParser(description="Explicit PulseOps seed utility")
    parser.add_argument("--services", action="store_true", help="create the sample API monitors")
    parser.add_argument("--history", action="store_true", help="create seven days of demo health history")
    parser.add_argument("--admin", action="store_true", help="create an administrator")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--email", default="admin@example.com")
    arguments = parser.parse_args()
    if not arguments.services and not arguments.history and not arguments.admin:
        parser.error("choose --services, --history, --admin, or a combination")
    app = create_app()
    with app.app_context():
        if arguments.services:
            seed_services()
        if arguments.history:
            seed_history()
        if arguments.admin:
            seed_admin(arguments.username.strip(), arguments.email.strip())


if __name__ == "__main__":
    main()
