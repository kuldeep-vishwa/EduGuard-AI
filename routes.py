"""
routes.py – EduGuard AI Main / Root Routes
==========================================
Home page, error handlers, and utility endpoints.
"""

from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Root: redirect authenticated users to their dashboard, else landing."""
    if current_user.is_authenticated:
        from models import RoleEnum
        role_map = {
            RoleEnum.ADMIN:   "admin.dashboard",
            RoleEnum.FACULTY: "faculty.dashboard",
            RoleEnum.STUDENT: "student.dashboard",
        }
        return redirect(url_for(role_map.get(current_user.role, "auth.login")))
    return render_template("landing.html", title="EduGuard AI – Early Warning System")


# ── Error handlers ────────────────────────────────────────────────────────────

@main_bp.app_errorhandler(404)
def not_found(e):
    return render_template("errors/404.html"), 404


@main_bp.app_errorhandler(403)
def forbidden(e):
    return render_template("errors/403.html"), 403


@main_bp.app_errorhandler(500)
def server_error(e):
    return render_template("errors/500.html"), 500
