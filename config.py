import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'service_health.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MONITOR_INTERVAL_SECONDS = int(os.getenv("MONITOR_INTERVAL_SECONDS", "60"))
    REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "8"))
    ALERT_FAILURE_THRESHOLD = int(os.getenv("ALERT_FAILURE_THRESHOLD", "2"))
    DEFAULT_RESPONSE_THRESHOLD_MS = int(os.getenv("DEFAULT_RESPONSE_THRESHOLD_MS", "1000"))
    DASHBOARD_REFRESH_SECONDS = int(os.getenv("DASHBOARD_REFRESH_SECONDS", "25"))
    HISTORY_RETENTION_DAYS = int(os.getenv("HISTORY_RETENTION_DAYS", "90"))
    SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"
    SCHEDULER_TICK_SECONDS = int(os.getenv("SCHEDULER_TICK_SECONDS", "10"))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
