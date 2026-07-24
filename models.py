"""
models.py – EduGuard AI Database Models
========================================
All SQLAlchemy ORM models for the application.
Fully normalised schema designed to support Phase 2 AI integration.

Tables:
    User              – Authentication table (all roles)
    Department        – Academic departments
    Subject           – Subjects linked to departments
    Unit              – Units within each subject
    Student           – Student profile
    Faculty           – Faculty profile
    Attendance        – Daily attendance records
    Assignment        – Assignment records per student per subject
    FacultyFeedback   – Qualitative feedback from faculty
    Question          – Question bank
    Assessment        – Scheduled assessments
    AssessmentAttempt – Student assessment session
    AssessmentAnswer  – Per-question answer within an attempt
    AcademicRecord    – Historical GPA / semester records
    AIAnalysisResult  – Cached IBM Granite AI analysis output
"""

import json
from datetime import datetime
from database import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


# ─────────────────────────────────────────────────────────────────────────────
# ENUMERATIONS  (stored as string columns for readability)
# ─────────────────────────────────────────────────────────────────────────────

class RoleEnum:
    ADMIN = "admin"
    FACULTY = "faculty"
    STUDENT = "student"
    ALL = [ADMIN, FACULTY, STUDENT]


class DifficultyEnum:
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    ALL = [EASY, MEDIUM, HARD]


class QuestionTypeEnum:
    MCQ = "mcq"
    TRUE_FALSE = "true_false"
    FILL_BLANK = "fill_blank"
    ALL = [MCQ, TRUE_FALSE, FILL_BLANK]


class AttendanceStatusEnum:
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    EXCUSED = "excused"


# ─────────────────────────────────────────────────────────────────────────────
# USER  (authentication – all roles share this table)
# ─────────────────────────────────────────────────────────────────────────────

class User(UserMixin, db.Model):
    """Central authentication table for all roles."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=RoleEnum.STUDENT)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    profile_picture = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    # Relationships
    student_profile = db.relationship("Student", back_populates="user", uselist=False, cascade="all, delete-orphan")
    faculty_profile = db.relationship("Faculty", back_populates="user", uselist=False, cascade="all, delete-orphan")

    # ── Password helpers ──────────────────────────────────────────────────────
    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    # ── Role helpers ──────────────────────────────────────────────────────────
    @property
    def is_admin(self) -> bool:
        return self.role == RoleEnum.ADMIN

    @property
    def is_faculty(self) -> bool:
        return self.role == RoleEnum.FACULTY

    @property
    def is_student(self) -> bool:
        return self.role == RoleEnum.STUDENT

    @property
    def display_name(self) -> str:
        if self.student_profile:
            return self.student_profile.full_name
        if self.faculty_profile:
            return self.faculty_profile.full_name
        return self.username

    def __repr__(self) -> str:
        return f"<User {self.username} [{self.role}]>"


# ─────────────────────────────────────────────────────────────────────────────
# DEPARTMENT
# ─────────────────────────────────────────────────────────────────────────────

class Department(db.Model):
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    subjects = db.relationship("Subject", back_populates="department", lazy="dynamic")
    students = db.relationship("Student", back_populates="department", lazy="dynamic")
    faculty_members = db.relationship("Faculty", back_populates="department", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Department {self.code}>"


# ─────────────────────────────────────────────────────────────────────────────
# SUBJECT
# ─────────────────────────────────────────────────────────────────────────────

class Subject(db.Model):
    __tablename__ = "subjects"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    credits = db.Column(db.Integer, default=3)
    semester = db.Column(db.Integer, nullable=True)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    department = db.relationship("Department", back_populates="subjects")
    units = db.relationship("Unit", back_populates="subject", cascade="all, delete-orphan", lazy="dynamic")
    questions = db.relationship("Question", back_populates="subject", lazy="dynamic")
    assessments = db.relationship("Assessment", back_populates="subject", lazy="dynamic")
    assignments = db.relationship("Assignment", back_populates="subject", lazy="dynamic")
    attendance_records = db.relationship("Attendance", back_populates="subject", lazy="dynamic")
    faculty_subjects = db.relationship("FacultySubject", back_populates="subject", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Subject {self.code}>"


# ─────────────────────────────────────────────────────────────────────────────
# UNIT
# ─────────────────────────────────────────────────────────────────────────────

class Unit(db.Model):
    __tablename__ = "units"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    unit_number = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text, nullable=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    subject = db.relationship("Subject", back_populates="units")
    questions = db.relationship("Question", back_populates="unit", lazy="dynamic")
    assessments = db.relationship("Assessment", back_populates="unit", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Unit {self.unit_number}: {self.name}>"


# ─────────────────────────────────────────────────────────────────────────────
# STUDENT
# ─────────────────────────────────────────────────────────────────────────────

class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    student_id = db.Column(db.String(30), unique=True, nullable=False, index=True)   # Enrollment number
    full_name = db.Column(db.String(150), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(20), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.Text, nullable=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
    current_semester = db.Column(db.Integer, default=1)
    batch_year = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Phase 2 – AI Risk Score (placeholder columns)
    academic_health_score = db.Column(db.Float, nullable=True)       # 0–100
    risk_level = db.Column(db.String(20), nullable=True)              # low / medium / high
    risk_updated_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    user = db.relationship("User", back_populates="student_profile")
    department = db.relationship("Department", back_populates="students")
    attendance_records = db.relationship("Attendance", back_populates="student", lazy="dynamic", cascade="all, delete-orphan")
    assignments = db.relationship("Assignment", back_populates="student", lazy="dynamic", cascade="all, delete-orphan")
    feedbacks = db.relationship("FacultyFeedback", back_populates="student", lazy="dynamic", cascade="all, delete-orphan")
    assessment_attempts = db.relationship("AssessmentAttempt", back_populates="student", lazy="dynamic", cascade="all, delete-orphan")
    academic_records = db.relationship("AcademicRecord", back_populates="student", lazy="dynamic", cascade="all, delete-orphan")

    @property
    def attendance_percentage(self) -> float:
        total = self.attendance_records.count()
        if total == 0:
            return 0.0
        present = self.attendance_records.filter_by(status=AttendanceStatusEnum.PRESENT).count()
        return round((present / total) * 100, 2)

    @property
    def latest_gpa(self) -> float:
        record = self.academic_records.order_by(AcademicRecord.semester.desc()).first()
        return record.gpa if record else 0.0

    def __repr__(self) -> str:
        return f"<Student {self.student_id}>"


# ─────────────────────────────────────────────────────────────────────────────
# FACULTY
# ─────────────────────────────────────────────────────────────────────────────

class Faculty(db.Model):
    __tablename__ = "faculty"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    faculty_id = db.Column(db.String(30), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(150), nullable=False)
    designation = db.Column(db.String(100), nullable=True)
    qualification = db.Column(db.String(200), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
    specialization = db.Column(db.String(200), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    joining_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    user = db.relationship("User", back_populates="faculty_profile")
    department = db.relationship("Department", back_populates="faculty_members")
    subjects_taught = db.relationship("FacultySubject", back_populates="faculty", lazy="dynamic")
    attendance_records = db.relationship("Attendance", back_populates="faculty", lazy="dynamic")
    feedbacks_given = db.relationship("FacultyFeedback", back_populates="faculty", lazy="dynamic")
    questions = db.relationship("Question", back_populates="faculty", lazy="dynamic")
    assessments = db.relationship("Assessment", back_populates="faculty", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Faculty {self.faculty_id}>"


# ─────────────────────────────────────────────────────────────────────────────
# FACULTY ↔ SUBJECT  (many-to-many association)
# ─────────────────────────────────────────────────────────────────────────────

class FacultySubject(db.Model):
    __tablename__ = "faculty_subjects"

    id = db.Column(db.Integer, primary_key=True)
    faculty_id = db.Column(db.Integer, db.ForeignKey("faculty.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

    faculty = db.relationship("Faculty", back_populates="subjects_taught")
    subject = db.relationship("Subject", back_populates="faculty_subjects")

    __table_args__ = (db.UniqueConstraint("faculty_id", "subject_id", name="uq_faculty_subject"),)


# ─────────────────────────────────────────────────────────────────────────────
# ATTENDANCE
# ─────────────────────────────────────────────────────────────────────────────

class Attendance(db.Model):
    __tablename__ = "attendance"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey("faculty.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default=AttendanceStatusEnum.PRESENT, nullable=False)
    remarks = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    student = db.relationship("Student", back_populates="attendance_records")
    subject = db.relationship("Subject", back_populates="attendance_records")
    faculty = db.relationship("Faculty", back_populates="attendance_records")

    __table_args__ = (db.UniqueConstraint("student_id", "subject_id", "date", name="uq_attendance"),)

    def __repr__(self) -> str:
        return f"<Attendance {self.student_id} {self.date} {self.status}>"


# ─────────────────────────────────────────────────────────────────────────────
# ASSIGNMENT
# ─────────────────────────────────────────────────────────────────────────────

class Assignment(db.Model):
    __tablename__ = "assignments"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey("faculty.id"), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    max_marks = db.Column(db.Float, default=100.0)
    obtained_marks = db.Column(db.Float, nullable=True)
    submission_date = db.Column(db.Date, nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    student = db.relationship("Student", back_populates="assignments")
    subject = db.relationship("Subject", back_populates="assignments")

    @property
    def percentage(self) -> float:
        if self.obtained_marks is None or self.max_marks == 0:
            return 0.0
        return round((self.obtained_marks / self.max_marks) * 100, 2)

    def __repr__(self) -> str:
        return f"<Assignment {self.title}>"


# ─────────────────────────────────────────────────────────────────────────────
# FACULTY FEEDBACK
# ─────────────────────────────────────────────────────────────────────────────

class FacultyFeedback(db.Model):
    __tablename__ = "faculty_feedback"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey("faculty.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=True)

    # Rated parameters (1–5 scale)
    class_participation = db.Column(db.Integer, nullable=False, default=3)   # 1–5
    subject_understanding = db.Column(db.Integer, nullable=False, default=3) # 1–5
    assignment_quality = db.Column(db.Integer, nullable=False, default=3)    # 1–5
    learning_progress = db.Column(db.Integer, nullable=False, default=3)     # 1–5

    overall_rating = db.Column(db.Float, nullable=True)   # auto-computed average
    comments = db.Column(db.Text, nullable=True)
    feedback_date = db.Column(db.Date, default=datetime.utcnow().date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    student = db.relationship("Student", back_populates="feedbacks")
    faculty = db.relationship("Faculty", back_populates="feedbacks_given")

    def compute_overall(self) -> None:
        """Compute and persist the average rating."""
        self.overall_rating = round(
            (self.class_participation + self.subject_understanding +
             self.assignment_quality + self.learning_progress) / 4, 2
        )

    def __repr__(self) -> str:
        return f"<FacultyFeedback student={self.student_id} faculty={self.faculty_id}>"


# ─────────────────────────────────────────────────────────────────────────────
# QUESTION BANK
# ─────────────────────────────────────────────────────────────────────────────

class Question(db.Model):
    __tablename__ = "questions"

    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    unit_id = db.Column(db.Integer, db.ForeignKey("units.id"), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey("faculty.id"), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20), default=QuestionTypeEnum.MCQ, nullable=False)
    difficulty = db.Column(db.String(20), default=DifficultyEnum.MEDIUM, nullable=False)

    # For MCQ / True-False
    option_a = db.Column(db.String(255), nullable=True)
    option_b = db.Column(db.String(255), nullable=True)
    option_c = db.Column(db.String(255), nullable=True)
    option_d = db.Column(db.String(255), nullable=True)

    correct_answer = db.Column(db.String(255), nullable=False)   # "a","b","c","d" or "true"/"false" or text
    explanation = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    subject = db.relationship("Subject", back_populates="questions")
    unit = db.relationship("Unit", back_populates="questions")
    faculty = db.relationship("Faculty", back_populates="questions")
    answers = db.relationship("AssessmentAnswer", back_populates="question", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Question {self.id} [{self.difficulty}]>"


# ─────────────────────────────────────────────────────────────────────────────
# ASSESSMENT  (scheduled by faculty)
# ─────────────────────────────────────────────────────────────────────────────

class Assessment(db.Model):
    __tablename__ = "assessments"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    unit_id = db.Column(db.Integer, db.ForeignKey("units.id"), nullable=True)
    faculty_id = db.Column(db.Integer, db.ForeignKey("faculty.id"), nullable=False)

    # Scheduling
    scheduled_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=True)
    duration_minutes = db.Column(db.Integer, default=30)

    # Question settings
    total_questions = db.Column(db.Integer, default=10)
    easy_count = db.Column(db.Integer, default=4)
    medium_count = db.Column(db.Integer, default=4)
    hard_count = db.Column(db.Integer, default=2)
    max_marks = db.Column(db.Float, default=10.0)

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    subject = db.relationship("Subject", back_populates="assessments")
    unit = db.relationship("Unit", back_populates="assessments")
    faculty = db.relationship("Faculty", back_populates="assessments")
    attempts = db.relationship("AssessmentAttempt", back_populates="assessment", lazy="dynamic", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Assessment {self.title}>"


# ─────────────────────────────────────────────────────────────────────────────
# ASSESSMENT ATTEMPT  (one row per student attempt)
# ─────────────────────────────────────────────────────────────────────────────

class AssessmentAttempt(db.Model):
    __tablename__ = "assessment_attempts"

    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey("assessments.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_at = db.Column(db.DateTime, nullable=True)
    total_questions = db.Column(db.Integer, default=0)
    correct_answers = db.Column(db.Integer, default=0)
    score = db.Column(db.Float, default=0.0)
    percentage = db.Column(db.Float, default=0.0)
    is_completed = db.Column(db.Boolean, default=False)
    time_taken_seconds = db.Column(db.Integer, nullable=True)

    # Relationships
    assessment = db.relationship("Assessment", back_populates="attempts")
    student = db.relationship("Student", back_populates="assessment_attempts")
    answers = db.relationship("AssessmentAnswer", back_populates="attempt", lazy="dynamic", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Attempt {self.id} score={self.score}>"


# ─────────────────────────────────────────────────────────────────────────────
# ASSESSMENT ANSWER  (per-question answer within one attempt)
# ─────────────────────────────────────────────────────────────────────────────

class AssessmentAnswer(db.Model):
    __tablename__ = "assessment_answers"

    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("assessment_attempts.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    selected_answer = db.Column(db.String(255), nullable=True)
    is_correct = db.Column(db.Boolean, default=False)
    marks_awarded = db.Column(db.Float, default=0.0)

    # Relationships
    attempt = db.relationship("AssessmentAttempt", back_populates="answers")
    question = db.relationship("Question", back_populates="answers")


# ─────────────────────────────────────────────────────────────────────────────
# ACADEMIC RECORD  (historical GPA per semester)
# ─────────────────────────────────────────────────────────────────────────────

class AcademicRecord(db.Model):
    __tablename__ = "academic_records"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    academic_year = db.Column(db.String(20), nullable=True)   # e.g. "2023-24"
    gpa = db.Column(db.Float, nullable=False, default=0.0)
    sgpa = db.Column(db.Float, nullable=True)                 # Semester GPA
    cgpa = db.Column(db.Float, nullable=True)                 # Cumulative GPA
    total_credits = db.Column(db.Integer, nullable=True)
    earned_credits = db.Column(db.Integer, nullable=True)
    backlogs = db.Column(db.Integer, default=0)
    remarks = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    student = db.relationship("Student", back_populates="academic_records")

    __table_args__ = (db.UniqueConstraint("student_id", "semester", name="uq_student_semester"),)

    def __repr__(self) -> str:
        return f"<AcademicRecord student={self.student_id} sem={self.semester} gpa={self.gpa}>"


# ─────────────────────────────────────────────────────────────────────────────
# AI ANALYSIS RESULT  (cached IBM Granite analysis output)
# ─────────────────────────────────────────────────────────────────────────────

class AIAnalysisResult(db.Model):
    """
    Stores cached IBM Granite AI analysis so the same result is not
    regenerated on every page load.

    analysis_type values:
        "assessment"  – post-assessment analysis linked to an AssessmentAttempt
        "risk_report" – full student risk report (daily refresh)
    """
    __tablename__ = "ai_analysis_results"

    id            = db.Column(db.Integer, primary_key=True)
    student_id    = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    attempt_id    = db.Column(db.Integer, db.ForeignKey("assessment_attempts.id"), nullable=True)
    analysis_type = db.Column(db.String(30), nullable=False, default="assessment")  # assessment | risk_report
    analysis_text = db.Column(db.Text, nullable=False)
    sections_json = db.Column(db.Text, nullable=True)   # JSON dict of parsed sections
    generated_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    student = db.relationship("Student", backref=db.backref("ai_analyses", lazy="dynamic"))

    def get_sections(self) -> dict:
        """Deserialise sections_json safely."""
        try:
            return json.loads(self.sections_json) if self.sections_json else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def __repr__(self) -> str:
        return f"<AIAnalysisResult student={self.student_id} type={self.analysis_type}>"
