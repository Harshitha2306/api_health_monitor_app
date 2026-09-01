from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.authz import admin_required
from app.extensions import db
from app.models import AuditLog
from app.services.audit import record_audit
from app.services.settings import SETTING_DEFINITIONS, get_setting, save_settings

admin_bp = Blueprint("admin", __name__)


@admin_bp.get("/audit-log")
@admin_required
def audit_log():
    page = request.args.get("page", 1, type=int)
    pagination = AuditLog.query.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=50, error_out=False)
    return render_template("admin/audit.html", logs=pagination.items, pagination=pagination)


@admin_bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    if request.method == "POST":
        errors = save_settings(request.form)
        if not errors:
            record_audit("settings_updated", "settings", None, "Updated application settings.")
            db.session.commit()
            flash("Settings updated.", "success")
            return redirect(url_for("admin.settings"))
        db.session.rollback()
        for message in errors.values():
            flash(message, "danger")
    values = {key: get_setting(key) for key in SETTING_DEFINITIONS}
    return render_template("admin/settings.html", definitions=SETTING_DEFINITIONS, values=values)


@admin_bp.get("/api-docs")
@login_required
def api_docs():
    return render_template("api_docs.html")
