# PulseOps

## API Monitoring and Service Health Management System

PulseOps is a professional Flask and SQLite monitoring platform. It periodically probes REST endpoints, measures latency and availability, detects sustained outages, manages incidents, and presents real monitoring evidence through a responsive operations console and versioned REST API.

The project is designed as a Master's-level software engineering system. It demonstrates modular architecture, background jobs, authentication, authorization, validation, metrics, auditability, exports, automated testing, and operational documentation without unnecessary infrastructure.

## Problem statement and objectives

REST APIs can become unavailable, return unexpected status codes, or respond slowly without immediately visible symptoms. PulseOps provides a central, durable view of endpoint health. Its objectives are to:

- Monitor HTTP and HTTPS endpoints at service-specific intervals.
- Record real response status, latency, health state, timestamp, and safe error details.
- Calculate 24-hour, 7-day, 30-day, and all-time uptime from stored checks.
- Reduce alert noise through configurable consecutive-failure thresholds.
- Provide dashboards, history, incidents, CSV reports, and a monitoring API.
- Demonstrate secure, testable, maintainable Flask application design.

## Core features

- GET, HEAD, and optional JSON POST probes using Python requests
- APScheduler monitoring with per-service due-time evaluation
- Healthy, Degraded, Down, Pending, and Paused service states
- Configurable interval, timeout, expected status, latency threshold, and failure threshold
- Failure streaks, duplicate-incident prevention, acknowledgement, and automatic recovery
- Incident start, recovery, ongoing time, and downtime duration
- Real-data KPIs, Chart.js charts, and a 40-block uptime timeline
- Full service CRUD and manual checks
- Filtered and paginated health/incident history
- CSV exports for checks, alerts, and uptime reports
- Admin and Viewer roles with Werkzeug hashing and Flask-Login
- CSRF protection for browser forms
- Administrative audit trail and persisted application settings
- System-health reporting for scheduler, database, monitors, and application uptime
- Consistent JSON errors, API documentation, responsive UI, and error pages
- Configurable 90-day monitoring-history cleanup

## Technology stack

| Area | Technology |
|---|---|
| Backend | Python, Flask |
| Data | SQLite, Flask-SQLAlchemy, Flask-Migrate |
| Authentication | Flask-Login, Werkzeug password hashing |
| Monitoring | requests |
| Scheduling | APScheduler |
| Frontend | Jinja2, HTML, CSS, vanilla JavaScript |
| Charts and icons | Chart.js CDN, Lucide CDN |
| Configuration | python-dotenv |
| Testing | pytest, unittest.mock |

## Architecture

    Browser
      |
      v
    Flask Web Interface
      |
      +---- Service Management
      |
      +---- Monitoring Dashboard
      |
      +---- Alert Management
      |
      +---- REST API
      |
      v
    Monitoring Service
      |
      v
    APScheduler
      |
      v
    HTTP Endpoint Checks
      |
      v
    HealthCheck + Alert Processing
      |
      v
    SQLite Database

The application factory configures extensions and blueprints. Route handlers validate requests and delegate probing, incident processing, metrics, settings, retention, and auditing to focused service modules. APScheduler opens an application context for each cycle and uses the same monitoring service as manual and API-triggered checks.

## Monitoring and alert workflow

    Configured Endpoint
           |
           v
        Scheduler
           |
           v
       HTTP Probe
           |
           +---- Success
           |       |
           |       v
           |   Record latency/status
           |   Reset failure streak
           |   Resolve active incident
           |
           +---- Failure
                   |
                   v
             Increase failure streak
                   |
                   v
            Alert threshold reached?
                   |
                   v
             Create incident alert

A correct HTTP status counts as available. When latency exceeds the service threshold, the observation is Degraded but still contributes to availability. A failed request or unexpected status is Down. Only one active incident can exist for a continuing outage. The next success resolves an Open or Acknowledged incident.

## Database entities

- **User:** username, email, password hash, role, and creation time.
- **MonitoredService:** endpoint configuration, scheduling/threshold settings, counters, and last-check timestamps.
- **HealthCheck:** status, response time, HTTP status, state, error, and timestamp.
- **Alert:** severity, message, status, lifecycle timestamps, and calculated duration.
- **AuditLog:** actor, action, entity, description, and timestamp.
- **ApplicationSetting:** persisted defaults and retention values.

Services cascade deletion to their checks and alerts. Indexes cover service, time, health state, severity, and alert status.

## Project structure

    app/
      api/monitoring.py
      routes/
        admin.py
        alerts.py
        auth.py
        dashboard.py
        history.py
        services.py
      services/
        audit.py
        maintenance.py
        metrics.py
        monitor.py
        scheduler.py
        settings.py
        validation.py
      static/css/app.css
      static/js/app.js
      templates/
      authz.py
      extensions.py
      models.py
      __init__.py
    config.py
    run.py
    seed.py
    tests/

## Installation

Python 3.10 or newer is recommended.

    python -m venv .venv
    .venv/Scripts/Activate.ps1
    python -m pip install -r requirements.txt

On macOS or Linux, activate with source .venv/bin/activate.

## Environment configuration

Edit `.env` and replace `SECRET_KEY` with a long random value. Important options include `DATABASE_URL`, `SCHEDULER_ENABLED`, `SCHEDULER_TICK_SECONDS`, `DASHBOARD_REFRESH_SECONDS`, and `HISTORY_RETENTION_DAYS`. Never commit `.env`.

## Database initialization and migrations

For a quick local run, the application creates missing tables. For migration-managed setup:

    $env:FLASK_APP = "run.py"
    flask db init
    flask db migrate -m "Initial PulseOps schema"
    flask db upgrade

After model changes, create and review a migration and run flask db upgrade. SQLite files under instance are git-ignored.

## Seed sample services and an administrator

Seeding is explicit. Sample services do not insert fake monitoring history:

    python seed.py --services

To populate the charts with seven days of deterministic demo observations:

    python seed.py --history

Create an administrator interactively:

    python seed.py --admin --username admin --email admin@example.com

For non-interactive setup, temporarily set PULSEOPS_ADMIN_PASSWORD to at least 10 characters:

    $env:PULSEOPS_ADMIN_PASSWORD = "replace-with-a-strong-password"
    python seed.py --admin --username admin --email admin@example.com
    Remove-Item Env:PULSEOPS_ADMIN_PASSWORD

Passwords are hashed before storage and are never logged.

## Start the application

    python run.py

Open http://127.0.0.1:5000. Debug mode is off unless FLASK_DEBUG=true. The scheduler is skipped during pytest and guarded against duplicate debug-reloader instances.

## Available pages

- / — overview, KPIs, charts, service status, and monitoring-engine health
- /login — account sign-in
- /services/ — monitored-service inventory
- /services/new — create monitor (Admin)
- /services/{id} — configuration, metrics, chart, timeline, and checks
- /services/{id}/edit — edit monitor (Admin)
- /alerts/ and /alerts/{id} — filtered incidents and details
- /history/ — filtered probe history and exports
- /api-docs — REST API reference
- /audit-log — administrative activity (Admin)
- /settings — defaults and retention configuration (Admin)

## REST API v1

| Method | Endpoint | Purpose |
|---|---|---|
| GET | /api/v1/health | Application and database health |
| GET | /api/v1/services | List services |
| GET | /api/v1/services/{id} | Get service |
| POST | /api/v1/services | Create service (Admin) |
| PUT | /api/v1/services/{id} | Update service (Admin) |
| DELETE | /api/v1/services/{id} | Delete service (Admin) |
| POST | /api/v1/services/{id}/check | Run check (Admin) |
| GET | /api/v1/services/{id}/history | Recent checks |
| GET | /api/v1/services/{id}/metrics | Uptime and latency |
| GET | /api/v1/alerts | Filterable incidents |
| GET | /api/v1/dashboard/summary | KPI, service, and chart data |

Errors contain an error object with a stable code and human-readable message. See /api-docs for request and response examples.

## Tests

External probes are mocked; pytest never requires internet access.

    python -m pytest -q

Coverage includes the empty dashboard, CRUD, API validation and CRUD, success/failure probes, threshold alerts, duplicate prevention, recovery, uptime, exports, authentication, and role permissions.

## Data retention

At 03:00 UTC, the scheduler calls the maintenance service. It deletes only HealthCheck rows older than the configured period (90 days by default); services, users, incidents, and audits are unaffected. Change the value on Settings or through HISTORY_RETENTION_DAYS. Set SCHEDULER_ENABLED=false if cleanup must never run automatically.

## Security considerations

- Passwords use salted hashes; no production password is hardcoded.
- State-changing browser forms use session CSRF tokens.
- Admin checks protect changes, manual probes, incident actions, settings, and audits.
- URL validation accepts only HTTP/HTTPS and rejects embedded credentials, localhost, loopback, link-local, unspecified literals, and unsupported schemes.
- User-facing probe errors are categorized; tracebacks remain in server logs.
- Cookies use HttpOnly and SameSite=Lax.
- POST probe bodies must be JSON; PulseOps never executes shell commands.

These application checks do not replace network policy. Production should add DNS rebinding defenses, outbound firewall or allow-list rules, redirect revalidation, HTTPS-only cookies, rate limiting, centralized secrets, and a production WSGI server.

## Logging

PulseOps logs startup, scheduler activity, probe results and failures, incident creation and recovery, retention cleanup, and administrative actions. Passwords are never logged.

## Screenshots

Portfolio screenshot placeholders:

- Overview dashboard
- Service detail and uptime timeline
- Incident dashboard
- Monitoring history

## Known limitations

- SQLite and an in-process scheduler suit a single-instance academic/demo deployment. Multiple workers require a dedicated scheduler and shared database.
- Availability is check-based rather than duration-weighted.
- Alerts are in-app; email, SMS, and webhooks are future work.
- SSRF protection is deliberately basic and needs network enforcement for untrusted production users.
- Chart.js, Lucide, and fonts use CDNs; core pages still work if those assets are unavailable.

## Future improvements

- Email and webhook channels with escalation policies
- Dedicated workers and distributed scheduler locking
- Teams, tenancy, and API-token authentication
- SLA targets, tags, maintenance windows, and public status pages
- Stronger DNS resolution and outbound network controls
- Duration-weighted availability and extended reports
