"""
blueprints/student/routes.py – EduGuard AI Student Blueprint
=============================================================
Student dashboard, assessment taking, history and academic records.
"""

import random
from datetime import datetime, date
from functools import wraps
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, jsonify, session)
from flask_login import login_required, current_user
from database import db
from models import (Student, Subject, Unit, Assessment, AssessmentAttempt,
                    AssessmentAnswer, Question, Attendance, Assignment,
                    FacultyFeedback, AcademicRecord, RoleEnum,
                    AttendanceStatusEnum)
from forms import AcademicRecordForm

student_bp = Blueprint("student", __name__, url_prefix="/student")


# ── Access guard ──────────────────────────────────────────────────────────────

def student_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_student:
            flash("Student access required.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def get_current_student():
    return Student.query.filter_by(user_id=current_user.id).first()


# ── Dashboard ─────────────────────────────────────────────────────────────────

@student_bp.route("/dashboard")
@login_required
@student_required
def dashboard():
    student = get_current_student()
    if not student:
        flash("Student profile not found. Contact admin.", "danger")
        return redirect(url_for("auth.logout"))

    # Attendance
    total_att = student.attendance_records.count()
    present_att = student.attendance_records.filter_by(
        status=AttendanceStatusEnum.PRESENT).count()
    att_pct = round((present_att / total_att * 100), 1) if total_att else 0

    # Assignments
    assignments = student.assignments.order_by(Assignment.created_at.desc()).limit(5).all()
    avg_assignment = 0
    all_assignments = student.assignments.filter(Assignment.obtained_marks.isnot(None)).all()
    if all_assignments:
        avg_assignment = round(
            sum(a.obtained_marks / a.max_marks * 100 for a in all_assignments) / len(all_assignments), 1
        )

    # Academic records / GPA
    academic_records = student.academic_records.order_by(AcademicRecord.semester).all()
    latest_gpa = academic_records[-1].gpa if academic_records else 0

    # Recent feedback
    recent_feedback = (student.feedbacks
                       .order_by(FacultyFeedback.created_at.desc())
                       .limit(3).all())

    # Assessment stats
    completed_attempts = (student.assessment_attempts
                          .filter_by(is_completed=True)
                          .order_by(AssessmentAttempt.submitted_at.desc())
                          .limit(5).all())
    total_attempts = student.assessment_attempts.filter_by(is_completed=True).count()
    avg_score = 0
    if total_attempts:
        from sqlalchemy import func
        result = db.session.query(func.avg(AssessmentAttempt.percentage)).filter_by(
            student_id=student.id, is_completed=True
        ).scalar()
        avg_score = round(result or 0, 1)

    # Upcoming assessments
    upcoming_assessments = (Assessment.query
                            .filter(Assessment.is_active == True,
                                    Assessment.scheduled_date >= date.today())
                            .order_by(Assessment.scheduled_date)
                            .limit(5).all())

    # Chart data: assessment scores over time
    chart_attempts = (student.assessment_attempts
                      .filter_by(is_completed=True)
                      .order_by(AssessmentAttempt.submitted_at)
                      .limit(10).all())
    chart_labels = [a.submitted_at.strftime("%d %b") if a.submitted_at else "" for a in chart_attempts]
    chart_scores = [a.percentage for a in chart_attempts]

    # Attendance subject-wise
    from sqlalchemy import func as sqlfunc
    from models import Subject as SubjectModel
    att_by_subject = (db.session.query(SubjectModel.name,
                                        sqlfunc.count(Attendance.id),
                                        sqlfunc.sum(
                                            db.case((Attendance.status == AttendanceStatusEnum.PRESENT, 1), else_=0)
                                        ))
                      .join(Attendance, Attendance.subject_id == SubjectModel.id)
                      .filter(Attendance.student_id == student.id)
                      .group_by(SubjectModel.id).all())

    # ── AI: Academic Health Score ─────────────────────────────────────────────
    from ai_service import get_student_health_score
    health = get_student_health_score(student)
    # Persist updated values
    student.academic_health_score = health["score"]
    student.risk_level            = health["risk_level"]
    db.session.commit()

    return render_template("student/dashboard.html",
                           title="Student Dashboard",
                           student=student,
                           att_pct=att_pct,
                           total_att=total_att,
                           avg_assignment=avg_assignment,
                           assignments=assignments,
                           academic_records=academic_records,
                           latest_gpa=latest_gpa,
                           recent_feedback=recent_feedback,
                           completed_attempts=completed_attempts,
                           total_attempts=total_attempts,
                           avg_score=avg_score,
                           upcoming_assessments=upcoming_assessments,
                           chart_labels=chart_labels,
                           chart_scores=chart_scores,
                           att_by_subject=att_by_subject,
                           health=health)


# ═════════════════════════════════════════════════════════════════════════════
# ASSESSMENTS
# ═════════════════════════════════════════════════════════════════════════════

@student_bp.route("/assessments")
@login_required
@student_required
def assessments():
    student = get_current_student()
    # Available assessments that haven't been completed
    all_assessments = (Assessment.query
                       .filter_by(is_active=True)
                       .filter(Assessment.scheduled_date <= date.today())
                       .order_by(Assessment.scheduled_date.desc())
                       .all())

    # Get attempt info per assessment
    completed_ids = set(
        a.assessment_id for a in student.assessment_attempts.filter_by(is_completed=True).all()
    )
    upcoming = (Assessment.query
                .filter_by(is_active=True)
                .filter(Assessment.scheduled_date > date.today())
                .order_by(Assessment.scheduled_date).all())

    return render_template("student/assessments.html",
                           title="Assessments",
                           student=student,
                           all_assessments=all_assessments,
                           completed_ids=completed_ids,
                           upcoming=upcoming)


@student_bp.route("/assessments/<int:assessment_id>/start")
@login_required
@student_required
def start_assessment(assessment_id):
    student = get_current_student()
    assessment = Assessment.query.get_or_404(assessment_id)

    # Check already completed
    existing = AssessmentAttempt.query.filter_by(
        assessment_id=assessment_id,
        student_id=student.id,
        is_completed=True
    ).first()
    if existing:
        flash("You have already completed this assessment.", "info")
        return redirect(url_for("student.assessments"))

    # Build question pool by difficulty
    def fetch_questions(difficulty, count):
        q = Question.query.filter_by(
            subject_id=assessment.subject_id,
            difficulty=difficulty,
            is_active=True
        )
        if assessment.unit_id:
            q = q.filter_by(unit_id=assessment.unit_id)
        pool = q.all()
        return random.sample(pool, min(count, len(pool)))

    questions = (
        fetch_questions("easy", assessment.easy_count) +
        fetch_questions("medium", assessment.medium_count) +
        fetch_questions("hard", assessment.hard_count)
    )
    random.shuffle(questions)

    if not questions:
        flash("No questions available for this assessment yet.", "warning")
        return redirect(url_for("student.assessments"))

    # Create attempt record
    attempt = AssessmentAttempt(
        assessment_id=assessment.id,
        student_id=student.id,
        total_questions=len(questions),
        is_completed=False
    )
    db.session.add(attempt)
    db.session.commit()

    # Store question IDs in session for this attempt
    session[f"attempt_{attempt.id}_questions"] = [q.id for q in questions]

    return render_template("student/take_assessment.html",
                           title=f"Assessment – {assessment.title}",
                           student=student,
                           assessment=assessment,
                           attempt=attempt,
                           questions=questions,
                           duration=assessment.duration_minutes)


@student_bp.route("/assessments/submit/<int:attempt_id>", methods=["POST"])
@login_required
@student_required
def submit_assessment(attempt_id):
    student = get_current_student()
    attempt = AssessmentAttempt.query.filter_by(
        id=attempt_id, student_id=student.id
    ).first_or_404()

    if attempt.is_completed:
        flash("Assessment already submitted.", "info")
        return redirect(url_for("student.assessment_result", attempt_id=attempt_id))

    question_ids = session.get(f"attempt_{attempt_id}_questions", [])
    questions = Question.query.filter(Question.id.in_(question_ids)).all()
    marks_per_question = attempt.assessment.max_marks / len(questions) if questions else 0

    correct = 0
    for q in questions:
        selected = request.form.get(f"answer_{q.id}", "").strip().lower()
        is_correct = (selected == q.correct_answer.strip().lower())
        if is_correct:
            correct += 1
        answer_record = AssessmentAnswer(
            attempt_id=attempt.id,
            question_id=q.id,
            selected_answer=selected,
            is_correct=is_correct,
            marks_awarded=marks_per_question if is_correct else 0
        )
        db.session.add(answer_record)

    attempt.correct_answers = correct
    attempt.score = round(correct * marks_per_question, 2)
    attempt.percentage = round((correct / len(questions)) * 100, 2) if questions else 0
    attempt.is_completed = True
    attempt.submitted_at = datetime.utcnow()
    # Time taken
    if attempt.started_at:
        attempt.time_taken_seconds = int((datetime.utcnow() - attempt.started_at).total_seconds())

    db.session.commit()

    # Clean up session
    session.pop(f"attempt_{attempt_id}_questions", None)
    flash("Assessment submitted successfully!", "success")
    return redirect(url_for("student.assessment_result", attempt_id=attempt_id))


@student_bp.route("/assessments/result/<int:attempt_id>")
@login_required
@student_required
def assessment_result(attempt_id):
    student = get_current_student()
    attempt = AssessmentAttempt.query.filter_by(
        id=attempt_id, student_id=student.id, is_completed=True
    ).first_or_404()

    answers = attempt.answers.all()

    # ── AI Analysis: auto-generate on first view ──────────────────────────────
    from ai_service import analyze_assessment as ai_analyze
    ai_result = ai_analyze(attempt_id)

    return render_template("student/assessment_result.html",
                           title="Assessment Result",
                           student=student,
                           attempt=attempt,
                           answers=answers,
                           ai_result=ai_result)


@student_bp.route("/history")
@login_required
@student_required
def history():
    student = get_current_student()
    page = request.args.get("page", 1, type=int)
    attempts = (student.assessment_attempts
                .filter_by(is_completed=True)
                .order_by(AssessmentAttempt.submitted_at.desc())
                .paginate(page=page, per_page=15))
    return render_template("student/history.html",
                           title="Assessment History",
                           student=student,
                           attempts=attempts)


# ═════════════════════════════════════════════════════════════════════════════
# ACADEMIC RECORDS
# ═════════════════════════════════════════════════════════════════════════════

@student_bp.route("/academic-records", methods=["GET", "POST"])
@login_required
@student_required
def academic_records():
    student = get_current_student()
    records = student.academic_records.order_by(AcademicRecord.semester).all()
    return render_template("student/academic_records.html",
                           title="Academic Records",
                           student=student,
                           records=records)


# ═════════════════════════════════════════════════════════════════════════════
# PROFILE
# ═════════════════════════════════════════════════════════════════════════════

@student_bp.route("/profile")
@login_required
@student_required
def profile():
    student = get_current_student()
    return render_template("student/profile.html",
                           title="My Profile",
                           student=student)
