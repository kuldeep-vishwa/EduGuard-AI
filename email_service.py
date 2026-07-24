"""
email_service.py – EduGuard AI  ·  Email Alert Service
=======================================================
Sends automated email alerts via Gmail SMTP using Flask-Mail.

Triggered when a student's Academic Health Score changes risk level:
  - Medium Risk  → yellow alert to faculty + student
  - High Risk    → red alert to faculty, student, and admin

Configuration (all in .env / config.py):
    MAIL_SERVER          = smtp.gmail.com
    MAIL_PORT            = 587
    MAIL_USE_TLS         = True
    MAIL_USERNAME        = your-gmail@gmail.com
    MAIL_PASSWORD        = your-app-password          ← Gmail App Password, not your real password
    MAIL_DEFAULT_SENDER  = EduGuard AI <your-gmail@gmail.com>

Gmail Setup:
    1. Enable 2-Step Verification on your Gmail account
    2. Go to https://myaccount.google.com/apppasswords
    3. Create an App Password for "Mail"
    4. Copy the 16-character password into MAIL_PASSWORD in .env

Usage:
    from email_service import send_risk_alert
    send_risk_alert(student)          # call after health score recalculation
"""

import logging
from typing import Optional

logger = logging.getLogger("eduguard.email_service")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[EduGuard Email] %(levelname)s – %(message)s"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)
    logger.propagate = False

# Module-level Flask-Mail instance (initialised in init_mail)
_mail = None


def init_mail(app):
    """
    Initialise Flask-Mail with the app.  Call this from create_app().
    Safe to call even if MAIL_USERNAME is not set – mail will be disabled.
    """
    global _mail
    try:
        from flask_mail import Mail
        _mail = Mail(app)
        if app.config.get("MAIL_USERNAME"):
            logger.info("Flask-Mail initialised. Sender: %s", app.config.get("MAIL_DEFAULT_SENDER"))
        else:
            logger.info("MAIL_USERNAME not set – email alerts are disabled.")
    except ImportError:
        logger.warning("flask-mail not installed. Run: pip install Flask-Mail>=0.10.0")
        _mail = None


def _is_email_configured() -> bool:
    """Return True if mail credentials are present and Flask-Mail is ready."""
    if _mail is None:
        return False
    try:
        from flask import current_app
        return bool(current_app.config.get("MAIL_USERNAME"))
    except RuntimeError:
        return False


def send_risk_alert(student) -> bool:
    """
    Send a risk-level email alert for a student.

    Determines recipients from the student's risk_level:
        low    → no email
        medium → email student + faculty who gave last feedback
        high   → email student + all faculty + admin email

    Returns True if at least one email was sent, False otherwise.
    """
    if not _is_email_configured():
        logger.info("Email not configured – skipping risk alert for student %s", student.student_id)
        return False

    risk = (student.risk_level or "low").lower()
    if risk == "low":
        return False  # No alert needed for low-risk students

    try:
        from flask import current_app
        from flask_mail import Message
        from models import FacultyFeedback, User, RoleEnum

        score = student.academic_health_score or 0
        risk_upper = risk.upper()

        subject_line = f"[EduGuard AI] {risk_upper} RISK ALERT – {student.full_name}"

        # ── Build recipient list ──────────────────────────────────────────────
        recipients = []

        # Always notify the student
        if student.user and student.user.email:
            recipients.append(student.user.email)

        # Notify faculty who have given feedback
        faculty_ids = (FacultyFeedback.query
                       .filter_by(student_id=student.id)
                       .with_entities(FacultyFeedback.faculty_id)
                       .distinct().all())
        for (fac_id,) in faculty_ids:
            from models import Faculty
            fac = Faculty.query.get(fac_id)
            if fac and fac.user and fac.user.email:
                recipients.append(fac.user.email)

        # For HIGH risk: also notify all admin users
        if risk == "high":
            admin_emails = (User.query.filter_by(role=RoleEnum.ADMIN, is_active=True)
                            .with_entities(User.email).all())
            for (email,) in admin_emails:
                recipients.append(email)

        if not recipients:
            logger.warning("No recipients found for risk alert (student %s)", student.student_id)
            return False

        # Remove duplicates
        recipients = list(set(recipients))

        # ── Build email body ──────────────────────────────────────────────────
        dept_name = student.department.name if student.department else "N/A"
        color = "🔴" if risk == "high" else "🟡"
        urgency = "IMMEDIATE ACTION REQUIRED" if risk == "high" else "Attention Required"

        body = f"""\
{color} EduGuard AI – Academic Risk Alert {color}
{'='*50}

{urgency}

Student Information:
  Name         : {student.full_name}
  Student ID   : {student.student_id}
  Department   : {dept_name}
  Semester     : {student.current_semester}

AI-Computed Academic Health:
  Health Score : {score:.1f} / 100
  Risk Level   : {risk_upper}

{'⚠️  This student is at HIGH risk of academic failure. Immediate faculty intervention is recommended.' if risk == 'high' else '⚠️  This student is showing signs of academic difficulty. Please monitor and provide support.'}

What to do next:
  1. Review the full AI Academic Report at:
     {current_app.config.get('MAIL_DEFAULT_SENDER', 'EduGuard AI')}
  2. Schedule a one-on-one counselling session with the student
  3. Review their recent attendance, assignment, and assessment records
  4. Provide targeted study recommendations

Risk Factors (based on Academic Health Score breakdown):
  • Attendance weight    : 30%
  • Assessment score     : 35%
  • Faculty feedback     : 20%
  • Assignment marks     : 10%
  • Previous GPA         :  5%

This is an automated alert from EduGuard AI.
Do not reply to this email. Log in to EduGuard AI for full details.
"""

        msg = Message(
            subject=subject_line,
            recipients=recipients,
            body=body,
            sender=current_app.config.get("MAIL_DEFAULT_SENDER") or current_app.config.get("MAIL_USERNAME"),
        )

        _mail.send(msg)
        logger.info(
            "Risk alert sent: student=%s risk=%s recipients=%d",
            student.student_id, risk_upper, len(recipients)
        )
        return True

    except Exception as exc:
        logger.error("Failed to send risk alert for student %s: %s", student.student_id, exc)
        return False


def send_test_email(to_address: str) -> bool:
    """
    Send a test email to verify SMTP configuration.
    Call from Flask shell: from email_service import send_test_email; send_test_email('you@example.com')
    """
    if not _is_email_configured():
        logger.error("Email not configured. Set MAIL_USERNAME and MAIL_PASSWORD in .env")
        return False
    try:
        from flask_mail import Message
        msg = Message(
            subject="[EduGuard AI] Test Email",
            recipients=[to_address],
            body="This is a test email from EduGuard AI.\n\nIf you received this, your SMTP configuration is working correctly.",
        )
        _mail.send(msg)
        logger.info("Test email sent to %s", to_address)
        return True
    except Exception as exc:
        logger.error("Test email failed: %s", exc)
        return False
