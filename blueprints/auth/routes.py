"""
blueprints/auth/routes.py – EduGuard AI Authentication Blueprint
=================================================================
Handles login, logout and password change for all roles.
"""

from datetime import datetime
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, session)
from flask_login import login_user, logout_user, login_required, current_user
from database import db
from models import User, RoleEnum
from forms import LoginForm, ChangePasswordForm

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


# ── Login ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Universal login page for all roles."""
    if current_user.is_authenticated:
        return redirect(_role_dashboard())

    form = LoginForm()
    if form.validate_on_submit():
        identifier = form.username.data.strip()
        # Allow login with username OR email
        user = (User.query.filter_by(username=identifier).first() or
                User.query.filter_by(email=identifier).first())

        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash("Your account has been deactivated. Contact admin.", "danger")
                return render_template("auth/login.html", form=form)

            login_user(user, remember=form.remember_me.data)
            user.last_login = datetime.utcnow()
            db.session.commit()

            flash(f"Welcome back, {user.display_name}!", "success")
            next_page = request.args.get("next")
            if next_page:
                return redirect(next_page)
            return redirect(_role_dashboard())

        flash("Invalid username or password.", "danger")

    return render_template("auth/login.html", form=form, title="Login – EduGuard AI")


# ── Logout ────────────────────────────────────────────────────────────────────

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("auth.login"))


# ── Change Password ────────────────────────────────────────────────────────────

@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("Current password is incorrect.", "danger")
        else:
            current_user.set_password(form.new_password.data)
            db.session.commit()
            flash("Password changed successfully.", "success")
            return redirect(_role_dashboard())
    return render_template("auth/change_password.html", form=form, title="Change Password")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _role_dashboard() -> str:
    """Return the correct dashboard URL for the current user's role."""
    role_map = {
        RoleEnum.ADMIN:   "admin.dashboard",
        RoleEnum.FACULTY: "faculty.dashboard",
        RoleEnum.STUDENT: "student.dashboard",
    }
    return url_for(role_map.get(current_user.role, "auth.login"))
