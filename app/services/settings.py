from flask import current_app

from app.extensions import db
from app.models import ApplicationSetting


SETTING_DEFINITIONS = {
    "default_interval_seconds": ("Default monitoring interval", 60, 10, 86400),
    "default_timeout_seconds": ("Default request timeout", 8, 1, 120),
    "default_failure_threshold": ("Default failure threshold", 3, 1, 100),
    "default_response_threshold_ms": ("Default response-time threshold", 1000, 1, 300000),
    "dashboard_refresh_seconds": ("Dashboard refresh frequency", 25, 10, 300),
    "history_retention_days": ("History retention", 90, 1, 3650),
}


def get_setting(key):
    definition = SETTING_DEFINITIONS[key]
    row = db.session.get(ApplicationSetting, key)
    if row:
        try:
            return int(row.value)
        except ValueError:
            return definition[1]
    config_map = {
        "default_interval_seconds": "MONITOR_INTERVAL_SECONDS",
        "default_timeout_seconds": "REQUEST_TIMEOUT_SECONDS",
        "default_failure_threshold": "ALERT_FAILURE_THRESHOLD",
        "default_response_threshold_ms": "DEFAULT_RESPONSE_THRESHOLD_MS",
        "dashboard_refresh_seconds": "DASHBOARD_REFRESH_SECONDS",
        "history_retention_days": "HISTORY_RETENTION_DAYS",
    }
    return int(current_app.config.get(config_map[key], definition[1]))


def save_settings(values):
    errors = {}
    for key, (_, _, minimum, maximum) in SETTING_DEFINITIONS.items():
        try:
            value = int(values.get(key, ""))
            if not minimum <= value <= maximum:
                raise ValueError
        except (TypeError, ValueError):
            errors[key] = f"Enter a value from {minimum} to {maximum}."
            continue
        row = db.session.get(ApplicationSetting, key) or ApplicationSetting(key=key)
        row.value = str(value)
        db.session.add(row)
    return errors
