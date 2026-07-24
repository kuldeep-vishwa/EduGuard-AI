"""
blueprints/ai/routes.py – EduGuard AI  ·  AI Feature Routes
=============================================================
All AI-related HTTP endpoints:
  - POST /ai/analyze-assessment/<attempt_id>   → trigger post-assessment analysis
  - GET  /ai/report/<student_id>               → full AI risk report page
  - POST /ai/chatbot                           → AJAX chatbot endpoint
  - GET  /ai/health-score/<student_id>         → JSON health score data
"""

from functools import wraps
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, jsonify)
from flask_login import login_required, current_user
from database import db
from models import Student, AssessmentAttempt, RoleEnum

ai_bp = Blueprint("ai", __name__, url_prefix="/ai")


# ── Access helpers ────────────────────────────────────────────────────────────

def _get_student_or_403(student_id: int):
    """
    Return a Student record the current user is authorised to view.
    Students can only view their own record; faculty and admin can view any.
    """
    student = Student.query.get_or_404(student_id)
    if current_user.is_student:
        own = Student.query.filter_by(user_id=current_user.id).first()
        if not own or own.id != student.id:
            return None
    return student


# ─────────────────────────────────────────────────────────────────────────────
# TRIGGER POST-ASSESSMENT AI ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

@ai_bp.route("/analyze-assessment/<int:attempt_id>", methods=["POST", "GET"])
@login_required
def analyze_assessment(attempt_id):
    """
    Trigger or retrieve IBM Granite analysis for a completed assessment attempt.
    Redirects back to the assessment result page after analysis is stored.
    """
    attempt = AssessmentAttempt.query.get_or_404(attempt_id)

    # Authorisation: student may only analyse their own attempt
    if current_user.is_student:
        own = Student.query.filter_by(user_id=current_user.id).first()
        if not own or attempt.student_id != own.id:
            flash("Unauthorised.", "danger")
            return redirect(url_for("student.assessments"))

    from ai_service import analyze_assessment as ai_analyze
    result = ai_analyze(attempt_id)

    if result:
        flash("AI analysis generated successfully.", "success")
    else:
        flash("AI analysis could not be generated right now.", "warning")

    return redirect(url_for("student.assessment_result", attempt_id=attempt_id))


# ─────────────────────────────────────────────────────────────────────────────
# AI REPORT PAGE
# ─────────────────────────────────────────────────────────────────────────────

@ai_bp.route("/report/<int:student_id>")
@login_required
def ai_report(student_id):
    """
    Full AI Risk Report page for a student.
    Students view their own; faculty/admin view any student.
    """
    student = _get_student_or_403(student_id)
    if not student:
        flash("You are not authorised to view this report.", "danger")
        if current_user.is_faculty:
            return redirect(url_for("faculty.student_list"))
        if current_user.is_admin:
            return redirect(url_for("admin.students"))
        return redirect(url_for("student.dashboard"))

    force = request.args.get("refresh", "0") == "1"

    from ai_service import generate_risk_report, get_student_health_score
    from models import AssessmentAttempt, AIAnalysisResult, FacultyFeedback
    from sqlalchemy import func

    risk_data  = generate_risk_report(student.id, force_refresh=force)
    health     = risk_data["health_data"] if risk_data else get_student_health_score(student)
    sections   = risk_data["sections"]   if risk_data else {}

    # Gather supporting data for the report page
    all_attempts = (student.assessment_attempts
                    .filter_by(is_completed=True)
                    .order_by(AssessmentAttempt.submitted_at.desc())
                    .all())
    avg_score = (db.session.query(func.avg(AssessmentAttempt.percentage))
                 .filter_by(student_id=student.id, is_completed=True).scalar() or 0)

    latest_analysis = (AIAnalysisResult.query
                       .filter_by(student_id=student.id, analysis_type="assessment")
                       .order_by(AIAnalysisResult.generated_at.desc())
                       .first())

    all_feedbacks = student.feedbacks.order_by(FacultyFeedback.created_at.desc()).all()
    avg_feedback = (db.session.query(func.avg(FacultyFeedback.overall_rating))
                    .filter_by(student_id=student.id).scalar() or 0)

    total_att = student.attendance_records.count()
    from models import AttendanceStatusEnum
    present   = student.attendance_records.filter_by(status=AttendanceStatusEnum.PRESENT).count()
    att_pct   = round((present / total_att * 100), 1) if total_att else 0

    academic_records = student.academic_records.order_by(db.text("semester")).all()

    # Choose template layout based on viewer role
    if current_user.is_admin:
        template = "ai/ai_report_admin.html"
    elif current_user.is_faculty:
        template = "ai/ai_report_faculty.html"
    else:
        template = "ai/ai_report.html"

    return render_template(
        template,
        title=f"AI Report – {student.full_name}",
        student=student,
        health=health,
        sections=sections,
        risk_data=risk_data,
        all_attempts=all_attempts,
        avg_score=round(avg_score, 1),
        latest_analysis=latest_analysis,
        all_feedbacks=all_feedbacks,
        avg_feedback=round(avg_feedback, 2),
        att_pct=att_pct,
        present=present,
        total_att=total_att,
        academic_records=academic_records,
    )


# ─────────────────────────────────────────────────────────────────────────────
# AI CHATBOT (AJAX endpoint)
# ─────────────────────────────────────────────────────────────────────────────

@ai_bp.route("/chatbot", methods=["POST"])
@login_required
def chatbot():
    """
    AJAX endpoint for the AI Academic Advisor chatbot.
    Accepts JSON body: {"message": "..."}
    Returns JSON: {"response": "..."}
    """
    data    = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()

    if not message:
        return jsonify({"response": "Please type a question to get started!"})

    student = None
    if current_user.is_student:
        student = Student.query.filter_by(user_id=current_user.id).first()

    from ai_service import chat_with_advisor
    response = chat_with_advisor(message, student=student)
    return jsonify({"response": response})


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH SCORE JSON  (for AJAX dashboard widgets)
# ─────────────────────────────────────────────────────────────────────────────

@ai_bp.route("/health-score/<int:student_id>")
@login_required
def health_score_json(student_id):
    """Return the academic health score as JSON for dashboard charts."""
    student = _get_student_or_403(student_id)
    if not student:
        return jsonify({"error": "Unauthorised"}), 403

    from ai_service import get_student_health_score
    health = get_student_health_score(student)

    # Persist to student record
    student.academic_health_score = health["score"]
    student.risk_level            = health["risk_level"]
    db.session.commit()

    return jsonify(health)
