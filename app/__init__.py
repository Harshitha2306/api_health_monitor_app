import logging
import os
import secrets
import time

from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user

from config import Config
from .extensions import db, login_manager, migrate

APPLICATION_STARTED_AT = time.time()


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    os.makedirs(app.instance_path, exist_ok=True)
    if app.testing:
        app.config["LOGIN_DISABLED"] = True
        app.config["SCHEDULER_ENABLED"] = False

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.blueprint == "monitoring_api":
            return jsonify({"error": {"code": "AUTHENTICATION_REQUIRED", "message": "Authentication is required for this operation."}}), 401
        return redirect(url_for("auth.login", next=request.full_path))

    from .api.monitoring import monitoring_api_bp
    from .routes.admin import admin_bp
    from .routes.alerts import alerts_bp
    from .routes.auth import auth_bp
    from .routes.dashboard import dashboard_bp
    from .routes.history import history_bp
    from .routes.services import services_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(services_bp, url_prefix="/services")
    app.register_blueprint(alerts_bp, url_prefix="/alerts")
    app.register_blueprint(history_bp, url_prefix="/history")
    app.register_blueprint(admin_bp)
    app.register_blueprint(monitoring_api_bp, url_prefix="/api/v1")

    @app.before_request
    def csrf_protection():
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not (
            request.blueprint == "monitoring_api" or app.testing
        ):
            if request.form.get("_csrf_token") != session.get("_csrf_token"):
                abort(400, description="Invalid or missing CSRF token.")

    @app.context_processor
    def template_utilities():
        def csrf_token():
            if "_csrf_token" not in session:
                session["_csrf_token"] = secrets.token_urlsafe(32)
            return session["_csrf_token"]

        def duration(value):
            value = max(0, int(value))
            hours, remainder = divmod(value, 3600)
            minutes, seconds = divmod(remainder, 60)
            parts = []
            if hours:
                parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
            if minutes:
                parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
            if seconds or not parts:
                parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
            return " ".join(parts)

        return {"csrf_token": csrf_token, "format_duration": duration}

    @app.errorhandler(403)
    def forbidden(error):
        if request.blueprint == "monitoring_api":
            return jsonify({"error": {"code": "FORBIDDEN", "message": "Administrator permission is required."}}), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    with app.app_context():
        db.create_all()

    from .services.scheduler import start_scheduler
    start_scheduler(app)
    app.logger.info("PulseOps application started")
    return app
