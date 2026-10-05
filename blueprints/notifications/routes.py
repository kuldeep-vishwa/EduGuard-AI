"""
blueprints/notifications/routes.py – EduGuard AI Notification Blueprint
========================================================================
AJAX endpoints for reading / marking notifications.
Notification generation helpers for all roles.
"""

from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from database import db
from models import Notification, NotificationPriorityEnum, NotificationTypeEnum

notifications_bp = Blueprint("notifications", __name__, url_prefix="/notifications")


# ── AJAX: fetch notifications for current user ────────────────────────────────

@notifications_bp.route("/fetch")
@login_required
def fetch():
    """Return latest 20 notifications for the logged-in user as JSON."""
    notifs = (current_user.notifications
              .order_by(Notification.created_at.desc())
              .limit(20).all())
    unread_count = current_user.notifications.filter_by(is_read=False).count()
    return jsonify({
        "unread_count": unread_count,
        "notifications": [_notif_to_dict(n) for n in notifs]
    })


# ── AJAX: mark one notification as read ──────────────────────────────────────

@notifications_bp.route("/<int:notif_id>/read", methods=["POST"])
@login_required
def mark_read(notif_id):
    notif = Notification.query.filter_by(id=notif_id, user_id=current_user.id).first_or_404()
    notif.mark_read()
    db.session.commit()
    return jsonify({"ok": True})


# ── AJAX: mark ALL as read ────────────────────────────────────────────────────

@notifications_bp.route("/mark-all-read", methods=["POST"])
@login_required
def mark_all_read():
    now = datetime.utcnow()
    (current_user.notifications
     .filter_by(is_read=False)
     .update({"is_read": True, "read_at": now}))
    db.session.commit()
    return jsonify({"ok": True})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _notif_to_dict(n: Notification) -> dict:
    return {
        "id":        n.id,
        "title":     n.title,
        "message":   n.message,
        "type":      n.notif_type,
        "priority":  n.priority,
        "is_read":   n.is_read,
        "created_at": n.created_at.strftime("%d %b %Y, %H:%M"),
    }


def _upsert_notification(user_id: int, source_key: str, title: str,
                          message: str, notif_type: str,
                          priority: str = NotificationPriorityEnum.NORMAL) -> None:
    """
    Create a notification only if the source_key has not been used before.
    This prevents duplicates on every dashboard refresh.
    """
    exists = Notification.query.filter_by(
        user_id=user_id, source_key=source_key
    ).first()
    if not exists:
        n = Notification(
            user_id=user_id,
            title=title,
            message=message,
            notif_type=notif_type,
            priority=priority,
            source_key=source_key,
        )
        db.session.add(n)


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC GENERATOR FUNCTIONS  (called from dashboard routes)
# ─────────────────────────────────────────────────────────────────────────────

def generate_student_notifications(student) -> None:
    """
    Generate idempotent notifications for a student based on current academic data.
    Called from the student dashboard route after health score is computed.
    """
    from models import AttendanceStatusEnum, AcademicRecord

    user_id = student.user_id

    # ── Risk level change ────────────────────────────────────────────────────
    risk = student.risk_level or "unknown"
    if risk == "high":
        _upsert_notification(
            user_id=user_id,
            source_key=f"risk:high:{student.id}",
            title="⚠️ High Academic Risk Detected",
            message=(
                f"Your Academic Health Score has dropped to {student.academic_health_score:.1f}/100. "
                "Please seek academic support immediately."
            ),
            notif_type=NotificationTypeEnum.RISK,
            priority=NotificationPriorityEnum.HIGH,
        )
    elif risk == "medium":
        _upsert_notification(
            user_id=user_id,
            source_key=f"risk:medium:{student.id}",
            title="📊 Academic Performance Needs Attention",
            message=(
                f"Your Academic Health Score is {student.academic_health_score:.1f}/100 (medium risk). "
                "Review your attendance and assignment submissions."
            ),
            notif_type=NotificationTypeEnum.RISK,
            priority=NotificationPriorityEnum.NORMAL,
        )

    # ── Low attendance ───────────────────────────────────────────────────────
    att_pct = student.attendance_percentage
    if att_pct < 75 and att_pct > 0:
        key = f"att:low:{student.id}:{int(att_pct)}"
        _upsert_notification(
            user_id=user_id,
            source_key=key,
            title="📅 Low Attendance Warning",
            message=(
                f"Your overall attendance is {att_pct}%, which is below the required 75%. "
                "Please attend classes regularly to avoid academic consequences."
            ),
            notif_type=NotificationTypeEnum.ATTENDANCE,
            priority=NotificationPriorityEnum.HIGH if att_pct < 60 else NotificationPriorityEnum.NORMAL,
        )

    # ── Low GPA / academic performance ──────────────────────────────────────
    latest_gpa = student.latest_gpa
    if 0 < latest_gpa < 5.0:
        _upsert_notification(
            user_id=user_id,
            source_key=f"gpa:low:{student.id}:{latest_gpa:.2f}",
            title="📉 Academic Performance Alert",
            message=(
                f"Your latest GPA is {latest_gpa:.2f}, which is below average. "
                "Consider seeking help from faculty or academic counselling."
            ),
            notif_type=NotificationTypeEnum.ACADEMIC,
            priority=NotificationPriorityEnum.NORMAL,
        )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def generate_faculty_notifications(faculty) -> None:
    """
    Generate idempotent notifications for a faculty member.
    Called from the faculty dashboard route.
    """
    from models import Student, Attendance
    from database import db as _db

    user_id = faculty.user_id

    # ── High-risk students requiring attention ───────────────────────────────
    student_ids_rows = (_db.session.query(Attendance.student_id)
                        .filter_by(faculty_id=faculty.id)
                        .distinct().all())
    student_ids = [s[0] for s in student_ids_rows]

    if student_ids:
        high_risk = Student.query.filter(
            Student.id.in_(student_ids),
            Student.risk_level == "high",
            Student.is_active == True
        ).all()

        for s in high_risk:
            _upsert_notification(
                user_id=user_id,
                source_key=f"faculty:risk:high:{s.id}",
                title=f"⚠️ High-Risk Student: {s.full_name}",
                message=(
                    f"{s.full_name} ({s.student_id}) has a high academic risk score of "
                    f"{s.academic_health_score:.1f}/100. Immediate intervention recommended."
                ),
                notif_type=NotificationTypeEnum.RISK,
                priority=NotificationPriorityEnum.HIGH,
            )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def generate_admin_notifications() -> None:
    """
    Generate idempotent system-level notifications for all admin users.
    Called from the admin dashboard route.
    """
    from models import Student, User, RoleEnum, AcademicRecordSubmission, RecordStatusEnum

    admins = User.query.filter_by(role=RoleEnum.ADMIN, is_active=True).all()
    if not admins:
        return

    # ── Count high-risk students ─────────────────────────────────────────────
    high_risk_count = Student.query.filter_by(is_active=True, risk_level="high").count()
    if high_risk_count > 0:
        for admin in admins:
            _upsert_notification(
                user_id=admin.id,
                source_key=f"admin:high_risk:{high_risk_count}",
                title=f"⚠️ {high_risk_count} High-Risk Students",
                message=(
                    f"There are currently {high_risk_count} students with a high academic risk level. "
                    "Review the student list and coordinate with faculty."
                ),
                notif_type=NotificationTypeEnum.RISK,
                priority=NotificationPriorityEnum.HIGH,
            )

    # ── Pending record approvals ─────────────────────────────────────────────
    pending_count = AcademicRecordSubmission.query.filter_by(
        status=RecordStatusEnum.PENDING
    ).count()
    if pending_count > 0:
        for admin in admins:
            _upsert_notification(
                user_id=admin.id,
                source_key=f"admin:pending_records:{pending_count}",
                title=f"📋 {pending_count} Pending Record Approval(s)",
                message=(
                    f"There are {pending_count} academic record submission(s) waiting for your review."
                ),
                notif_type=NotificationTypeEnum.SYSTEM,
                priority=NotificationPriorityEnum.NORMAL,
            )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
