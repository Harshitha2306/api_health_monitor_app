import logging

from flask_login import current_user

from app.extensions import db
from app.models import AuditLog


def record_audit(action, entity_type, entity_id, description):
    user_id = current_user.id if current_user.is_authenticated else None
    db.session.add(AuditLog(
        user_id=user_id, action=action, entity_type=entity_type,
        entity_id=entity_id, description=description[:500],
    ))
    logging.getLogger(__name__).info("%s: %s", action, description)
