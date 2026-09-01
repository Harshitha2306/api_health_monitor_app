from datetime import timedelta

from app.extensions import db
from app.models import HealthCheck, utcnow
from app.services.settings import get_setting


def delete_expired_health_checks(retention_days=None):
    days = retention_days or get_setting("history_retention_days")
    cutoff = utcnow() - timedelta(days=days)
    deleted = HealthCheck.query.filter(HealthCheck.checked_at < cutoff).delete(synchronize_session=False)
    db.session.commit()
    return deleted
