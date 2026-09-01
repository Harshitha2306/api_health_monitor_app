from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from app.models import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        user = User.query.filter(
            (User.username == identity) | (User.email == identity.lower())
        ).first()
        if user and user.check_password(request.form.get("password", "")):
            login_user(user, remember=bool(request.form.get("remember")))
            target = request.args.get("next")
            if target and not urlparse(target).netloc and target.startswith("/"):
                return redirect(target)
            return redirect(url_for("dashboard.index"))
        flash("Invalid username/email or password.", "danger")
    return render_template("auth/login.html")


@auth_bp.post("/logout")
def logout():
    logout_user()
    flash("You have been signed out.", "success")
    return redirect(url_for("auth.login"))
