"""
blueprints/admin/routes.py – EduGuard AI Admin Blueprint
=========================================================
Full CRUD for: Departments, Subjects, Units, Students, Faculty.
Dashboard analytics and CSV upload.
"""

import csv
import io
import os
from datetime import datetime, date
from functools import wraps
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, jsonify, current_app)
from flask_login import login_required, current_user
from sqlalchemy import func
from werkzeug.utils import secure_filename
from database import db
from models import (User, Student, Faculty, Department, Subject, Unit,
                    Attendance, Assignment, FacultyFeedback, Question,
                    Assessment, AssessmentAttempt, AcademicRecord,
                    FacultySubject, RoleEnum)
from forms import (DepartmentForm, SubjectForm, UnitForm, StudentForm,
                   FacultyForm, StudentCSVUploadForm, AcademicRecordForm)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# ── Access Guard ──────────────────────────────────────────────────────────────

def admin_required(f):
    """Decorator: restrict route to admin users only."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Admin access required.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


# ── Dashboard ─────────────────────────────────────────────────────────────────

@admin_bp.route("/dashboard")
@login_required
@admin_required
def dashboard():
    stats = {
        "total_students": Student.query.filter_by(is_active=True).count(),
        "total_faculty": Faculty.query.filter_by(is_active=True).count(),
        "total_departments": Department.query.filter_by(is_active=True).count(),
        "total_subjects": Subject.query.filter_by(is_active=True).count(),
        "total_questions": Question.query.filter_by(is_active=True).count(),
        "total_assessments": Assessment.query.filter_by(is_active=True).count(),
        "total_attempts": AssessmentAttempt.query.filter_by(is_completed=True).count(),
    }

    # Recent students
    recent_students = (Student.query
                       .join(User)
                       .order_by(Student.created_at.desc())
                       .limit(5).all())

    # Department-wise student distribution for chart
    dept_data = (db.session.query(Department.name, func.count(Student.id))
                 .join(Student, Student.department_id == Department.id, isouter=True)
                 .group_by(Department.id).all())
    dept_labels = [d[0] for d in dept_data]
    dept_counts = [d[1] for d in dept_data]

    # AI Risk Distribution: count students by risk_level
    risk_low    = Student.query.filter_by(is_active=True, risk_level="low").count()
    risk_medium = Student.query.filter_by(is_active=True, risk_level="medium").count()
    risk_high   = Student.query.filter_by(is_active=True, risk_level="high").count()
    risk_unknown = stats["total_students"] - risk_low - risk_medium - risk_high

    # At-risk students (high risk) for quick intervention list
    at_risk_students = (Student.query
                        .filter_by(is_active=True, risk_level="high")
                        .order_by(Student.risk_updated_at.desc())
                        .limit(8).all())

    return render_template("admin/dashboard.html",
                           title="Admin Dashboard",
                           stats=stats,
                           recent_students=recent_students,
                           dept_labels=dept_labels,
                           dept_counts=dept_counts,
                           risk_low=risk_low,
                           risk_medium=risk_medium,
                           risk_high=risk_high,
                           risk_unknown=risk_unknown,
                           at_risk_students=at_risk_students)


# ═════════════════════════════════════════════════════════════════════════════
# DEPARTMENTS
# ═════════════════════════════════════════════════════════════════════════════

@admin_bp.route("/departments")
@login_required
@admin_required
def departments():
    depts = Department.query.order_by(Department.name).all()
    return render_template("admin/departments.html",
                           title="Departments", departments=depts)


@admin_bp.route("/departments/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_department():
    form = DepartmentForm()
    if form.validate_on_submit():
        if Department.query.filter_by(code=form.code.data.upper()).first():
            flash("Department code already exists.", "warning")
        else:
            dept = Department(
                name=form.name.data,
                code=form.code.data.upper(),
                description=form.description.data,
                is_active=form.is_active.data
            )
            db.session.add(dept)
            db.session.commit()
            flash("Department added successfully.", "success")
            return redirect(url_for("admin.departments"))
    return render_template("admin/department_form.html",
                           form=form, title="Add Department")


@admin_bp.route("/departments/<int:dept_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_department(dept_id):
    dept = Department.query.get_or_404(dept_id)
    form = DepartmentForm(obj=dept)
    if form.validate_on_submit():
        dept.name = form.name.data
        dept.code = form.code.data.upper()
        dept.description = form.description.data
        dept.is_active = form.is_active.data
        db.session.commit()
        flash("Department updated.", "success")
        return redirect(url_for("admin.departments"))
    return render_template("admin/department_form.html",
                           form=form, title="Edit Department", edit=True)


@admin_bp.route("/departments/<int:dept_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_department(dept_id):
    dept = Department.query.get_or_404(dept_id)
    dept.is_active = False
    db.session.commit()
    flash("Department deactivated.", "info")
    return redirect(url_for("admin.departments"))


# ═════════════════════════════════════════════════════════════════════════════
# SUBJECTS
# ═════════════════════════════════════════════════════════════════════════════

@admin_bp.route("/subjects")
@login_required
@admin_required
def subjects():
    subjects_list = (Subject.query
                     .join(Department)
                     .order_by(Department.name, Subject.name).all())
    return render_template("admin/subjects.html",
                           title="Subjects", subjects=subjects_list)


@admin_bp.route("/subjects/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_subject():
    form = SubjectForm()
    form.department_id.choices = [(d.id, d.name) for d in Department.query.filter_by(is_active=True).all()]
    if form.validate_on_submit():
        if Subject.query.filter_by(code=form.code.data.upper()).first():
            flash("Subject code already exists.", "warning")
        else:
            subj = Subject(
                name=form.name.data,
                code=form.code.data.upper(),
                credits=form.credits.data,
                semester=form.semester.data,
                description=form.description.data,
                department_id=form.department_id.data,
                is_active=form.is_active.data
            )
            db.session.add(subj)
            db.session.commit()
            flash("Subject added.", "success")
            return redirect(url_for("admin.subjects"))
    return render_template("admin/subject_form.html", form=form, title="Add Subject")


@admin_bp.route("/subjects/<int:subj_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_subject(subj_id):
    subj = Subject.query.get_or_404(subj_id)
    form = SubjectForm(obj=subj)
    form.department_id.choices = [(d.id, d.name) for d in Department.query.filter_by(is_active=True).all()]
    if form.validate_on_submit():
        subj.name = form.name.data
        subj.code = form.code.data.upper()
        subj.credits = form.credits.data
        subj.semester = form.semester.data
        subj.description = form.description.data
        subj.department_id = form.department_id.data
        subj.is_active = form.is_active.data
        db.session.commit()
        flash("Subject updated.", "success")
        return redirect(url_for("admin.subjects"))
    return render_template("admin/subject_form.html",
                           form=form, title="Edit Subject", edit=True)


@admin_bp.route("/subjects/<int:subj_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_subject(subj_id):
    subj = Subject.query.get_or_404(subj_id)
    subj.is_active = False
    db.session.commit()
    flash("Subject deactivated.", "info")
    return redirect(url_for("admin.subjects"))


@admin_bp.route("/subjects/<int:subj_id>/units", methods=["GET"])
@login_required
@admin_required
def subject_units(subj_id):
    subj = Subject.query.get_or_404(subj_id)
    units = Unit.query.filter_by(subject_id=subj_id).order_by(Unit.unit_number).all()
    return render_template("admin/units.html",
                           title=f"Units – {subj.name}", subject=subj, units=units)


@admin_bp.route("/units/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_unit():
    from forms import UnitForm
    form = UnitForm()
    form.subject_id.choices = [(s.id, f"{s.code} – {s.name}") for s in Subject.query.filter_by(is_active=True).all()]
    if form.validate_on_submit():
        unit = Unit(
            name=form.name.data,
            unit_number=form.unit_number.data,
            description=form.description.data,
            subject_id=form.subject_id.data
        )
        db.session.add(unit)
        db.session.commit()
        flash("Unit added.", "success")
        return redirect(url_for("admin.subject_units", subj_id=form.subject_id.data))
    return render_template("admin/unit_form.html", form=form, title="Add Unit")


@admin_bp.route("/units/<int:unit_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_unit(unit_id):
    from forms import UnitForm
    unit = Unit.query.get_or_404(unit_id)
    form = UnitForm(obj=unit)
    form.subject_id.choices = [(s.id, f"{s.code} – {s.name}") for s in Subject.query.filter_by(is_active=True).all()]
    if form.validate_on_submit():
        unit.name = form.name.data
        unit.unit_number = form.unit_number.data
        unit.description = form.description.data
        unit.subject_id = form.subject_id.data
        db.session.commit()
        flash("Unit updated.", "success")
        return redirect(url_for("admin.subject_units", subj_id=unit.subject_id))
    return render_template("admin/unit_form.html", form=form, title="Edit Unit", edit=True)


@admin_bp.route("/units/<int:unit_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_unit(unit_id):
    unit = Unit.query.get_or_404(unit_id)
    subj_id = unit.subject_id
    db.session.delete(unit)
    db.session.commit()
    flash("Unit deleted.", "info")
    return redirect(url_for("admin.subject_units", subj_id=subj_id))


# ═════════════════════════════════════════════════════════════════════════════
# STUDENTS
# ═════════════════════════════════════════════════════════════════════════════

@admin_bp.route("/students")
@login_required
@admin_required
def students():
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "").strip()
    dept_filter = request.args.get("dept", 0, type=int)

    query = Student.query.join(User)
    if search:
        query = query.filter(
            (Student.full_name.ilike(f"%{search}%")) |
            (Student.student_id.ilike(f"%{search}%")) |
            (User.email.ilike(f"%{search}%"))
        )
    if dept_filter:
        query = query.filter(Student.department_id == dept_filter)

    per_page = current_app.config.get("ITEMS_PER_PAGE", 15)
    students_page = query.order_by(Student.full_name).paginate(page=page, per_page=per_page)
    departments = Department.query.filter_by(is_active=True).all()

    return render_template("admin/students.html",
                           title="Students",
                           students=students_page,
                           departments=departments,
                           search=search,
                           dept_filter=dept_filter)


@admin_bp.route("/students/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_student():
    form = StudentForm()
    form.department_id.choices = [(0, "Select Department")] + [
        (d.id, d.name) for d in Department.query.filter_by(is_active=True).all()
    ]
    if form.validate_on_submit():
        # Check for duplicates
        if User.query.filter_by(username=form.username.data).first():
            flash("Username already taken.", "warning")
        elif User.query.filter_by(email=form.email.data).first():
            flash("Email already registered.", "warning")
        elif Student.query.filter_by(student_id=form.student_id.data).first():
            flash("Student ID already exists.", "warning")
        else:
            user = User(username=form.username.data,
                        email=form.email.data,
                        role=RoleEnum.STUDENT)
            user.set_password(form.password.data or form.student_id.data)
            db.session.add(user)
            db.session.flush()

            student = Student(
                user_id=user.id,
                student_id=form.student_id.data,
                full_name=form.full_name.data,
                date_of_birth=form.date_of_birth.data,
                gender=form.gender.data,
                phone=form.phone.data,
                address=form.address.data,
                department_id=form.department_id.data or None,
                current_semester=form.current_semester.data or 1,
                batch_year=form.batch_year.data,
                is_active=form.is_active.data
            )
            db.session.add(student)
            db.session.commit()
            flash(f"Student {form.full_name.data} added successfully.", "success")
            return redirect(url_for("admin.students"))
    return render_template("admin/student_form.html", form=form, title="Add Student")


@admin_bp.route("/students/<int:student_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_student(student_id):
    student = Student.query.get_or_404(student_id)
    form = StudentForm(obj=student)
    form.department_id.choices = [(0, "Select Department")] + [
        (d.id, d.name) for d in Department.query.filter_by(is_active=True).all()
    ]
    if request.method == "GET":
        form.username.data = student.user.username
        form.email.data = student.user.email

    if form.validate_on_submit():
        student.user.username = form.username.data
        student.user.email = form.email.data
        if form.password.data:
            student.user.set_password(form.password.data)
        student.full_name = form.full_name.data
        student.date_of_birth = form.date_of_birth.data
        student.gender = form.gender.data
        student.phone = form.phone.data
        student.address = form.address.data
        student.department_id = form.department_id.data or None
        student.current_semester = form.current_semester.data or 1
        student.batch_year = form.batch_year.data
        student.is_active = form.is_active.data
        db.session.commit()
        flash("Student updated.", "success")
        return redirect(url_for("admin.students"))
    return render_template("admin/student_form.html",
                           form=form, title="Edit Student", edit=True, student=student)


@admin_bp.route("/students/<int:student_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    student.is_active = False
    student.user.is_active = False
    db.session.commit()
    flash("Student deactivated.", "info")
    return redirect(url_for("admin.students"))


@admin_bp.route("/students/<int:student_id>/view")
@login_required
@admin_required
def view_student(student_id):
    student = Student.query.get_or_404(student_id)
    attendance = student.attendance_records.order_by(Attendance.date.desc()).limit(30).all()
    assignments = student.assignments.order_by(Assignment.created_at.desc()).limit(10).all()
    feedbacks = student.feedbacks.order_by(FacultyFeedback.created_at.desc()).limit(5).all()
    academic_records = student.academic_records.order_by(AcademicRecord.semester).all()
    attempts = (student.assessment_attempts
                .filter_by(is_completed=True)
                .order_by(AssessmentAttempt.submitted_at.desc())
                .limit(10).all())
    return render_template("admin/student_detail.html",
                           title=f"Student – {student.full_name}",
                           student=student,
                           attendance=attendance,
                           assignments=assignments,
                           feedbacks=feedbacks,
                           academic_records=academic_records,
                           attempts=attempts)


@admin_bp.route("/students/upload-csv", methods=["GET", "POST"])
@login_required
@admin_required
def upload_students_csv():
    form = StudentCSVUploadForm()
    results = None
    if form.validate_on_submit():
        file = form.csv_file.data
        filename = secure_filename(file.filename)
        csv_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], "csv")
        os.makedirs(csv_dir, exist_ok=True)   # FIX: create dir if missing
        filepath = os.path.join(csv_dir, filename)
        file.save(filepath)

        success, errors = 0, []
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader, start=2):
                try:
                    # Expected columns: full_name,student_id,email,username,department_code,semester,batch_year
                    dept = Department.query.filter_by(code=row.get("department_code", "").upper()).first()
                    if User.query.filter_by(username=row["username"]).first():
                        errors.append(f"Row {i}: Username '{row['username']}' exists.")
                        continue
                    user = User(username=row["username"], email=row["email"], role=RoleEnum.STUDENT)
                    user.set_password(row.get("password", row["student_id"]))
                    db.session.add(user)
                    db.session.flush()
                    student = Student(
                        user_id=user.id,
                        student_id=row["student_id"],
                        full_name=row["full_name"],
                        department_id=dept.id if dept else None,
                        current_semester=int(row.get("semester", 1)),
                        batch_year=int(row.get("batch_year", datetime.utcnow().year))
                    )
                    db.session.add(student)
                    success += 1
                except Exception as e:
                    errors.append(f"Row {i}: {str(e)}")
        db.session.commit()
        results = {"success": success, "errors": errors}
        flash(f"Import complete: {success} students added, {len(errors)} errors.", "info")

    return render_template("admin/upload_csv.html",
                           form=form, title="Upload Students CSV", results=results)


# ═════════════════════════════════════════════════════════════════════════════
# FACULTY
# ═════════════════════════════════════════════════════════════════════════════

@admin_bp.route("/faculty")
@login_required
@admin_required
def faculty_list():
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "").strip()
    query = Faculty.query.join(User)
    if search:
        query = query.filter(
            (Faculty.full_name.ilike(f"%{search}%")) |
            (Faculty.faculty_id.ilike(f"%{search}%")) |
            (User.email.ilike(f"%{search}%"))
        )
    per_page = current_app.config.get("ITEMS_PER_PAGE", 15)
    faculty_page = query.order_by(Faculty.full_name).paginate(page=page, per_page=per_page)
    return render_template("admin/faculty.html",
                           title="Faculty", faculty=faculty_page, search=search)


@admin_bp.route("/faculty/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_faculty():
    form = FacultyForm()
    form.department_id.choices = [(0, "Select Department")] + [
        (d.id, d.name) for d in Department.query.filter_by(is_active=True).all()
    ]
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash("Username already taken.", "warning")
        elif User.query.filter_by(email=form.email.data).first():
            flash("Email already registered.", "warning")
        elif Faculty.query.filter_by(faculty_id=form.faculty_id.data).first():
            flash("Faculty ID already exists.", "warning")
        else:
            user = User(username=form.username.data,
                        email=form.email.data,
                        role=RoleEnum.FACULTY)
            user.set_password(form.password.data or form.faculty_id.data)
            db.session.add(user)
            db.session.flush()
            faculty = Faculty(
                user_id=user.id,
                faculty_id=form.faculty_id.data,
                full_name=form.full_name.data,
                designation=form.designation.data,
                qualification=form.qualification.data,
                phone=form.phone.data,
                department_id=form.department_id.data or None,
                specialization=form.specialization.data,
                joining_date=form.joining_date.data,
                is_active=form.is_active.data
            )
            db.session.add(faculty)
            db.session.commit()
            flash(f"Faculty {form.full_name.data} added.", "success")
            return redirect(url_for("admin.faculty_list"))
    return render_template("admin/faculty_form.html", form=form, title="Add Faculty")


@admin_bp.route("/faculty/<int:faculty_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_faculty(faculty_id):
    faculty = Faculty.query.get_or_404(faculty_id)
    form = FacultyForm(obj=faculty)
    form.department_id.choices = [(0, "Select Department")] + [
        (d.id, d.name) for d in Department.query.filter_by(is_active=True).all()
    ]
    if request.method == "GET":
        form.username.data = faculty.user.username
        form.email.data = faculty.user.email

    if form.validate_on_submit():
        faculty.user.username = form.username.data
        faculty.user.email = form.email.data
        if form.password.data:
            faculty.user.set_password(form.password.data)
        faculty.full_name = form.full_name.data
        faculty.designation = form.designation.data
        faculty.qualification = form.qualification.data
        faculty.phone = form.phone.data
        faculty.department_id = form.department_id.data or None
        faculty.specialization = form.specialization.data
        faculty.joining_date = form.joining_date.data
        faculty.is_active = form.is_active.data
        db.session.commit()
        flash("Faculty updated.", "success")
        return redirect(url_for("admin.faculty_list"))
    return render_template("admin/faculty_form.html",
                           form=form, title="Edit Faculty", edit=True, faculty=faculty)


@admin_bp.route("/faculty/<int:faculty_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_faculty(faculty_id):
    faculty = Faculty.query.get_or_404(faculty_id)
    faculty.is_active = False
    faculty.user.is_active = False
    db.session.commit()
    flash("Faculty deactivated.", "info")
    return redirect(url_for("admin.faculty_list"))


@admin_bp.route("/faculty/<int:faculty_id>/view")
@login_required
@admin_required
def view_faculty(faculty_id):
    faculty = Faculty.query.get_or_404(faculty_id)
    subjects = faculty.subjects_taught.all()
    all_subjects = Subject.query.filter_by(is_active=True).order_by(Subject.name).all()
    assigned_ids = {fs.subject_id for fs in subjects}
    return render_template("admin/faculty_detail.html",
                           title=f"Faculty – {faculty.full_name}",
                           faculty=faculty,
                           subjects=subjects,
                           all_subjects=all_subjects,
                           assigned_ids=assigned_ids)


@admin_bp.route("/faculty/<int:faculty_id>/assign-subjects", methods=["POST"])
@login_required
@admin_required
def assign_subjects(faculty_id):
    """Assign or remove subjects for a faculty member."""
    faculty = Faculty.query.get_or_404(faculty_id)
    selected_ids = request.form.getlist("subject_ids", type=int)

    # Remove all existing assignments then add the selected ones
    FacultySubject.query.filter_by(faculty_id=faculty.id).delete()
    for subj_id in selected_ids:
        if Subject.query.get(subj_id):
            db.session.add(FacultySubject(faculty_id=faculty.id, subject_id=subj_id))

    db.session.commit()
    flash(f"Subject assignments updated for {faculty.full_name}.", "success")
    return redirect(url_for("admin.view_faculty", faculty_id=faculty_id))


# ── AJAX: get units by subject ─────────────────────────────────────────────

@admin_bp.route("/api/units/<int:subject_id>")
@login_required
def get_units(subject_id):
    units = Unit.query.filter_by(subject_id=subject_id).order_by(Unit.unit_number).all()
    return jsonify([{"id": u.id, "name": f"Unit {u.unit_number}: {u.name}"} for u in units])


# ═════════════════════════════════════════════════════════════════════════════
# BULK IMPORT – Students + Faculty (CSV and XLSX via pandas)
# ═════════════════════════════════════════════════════════════════════════════

@admin_bp.route("/import/bulk", methods=["GET", "POST"])
@login_required
@admin_required
def bulk_import():
    """
    Bulk import Students or Faculty from CSV or XLSX files.
    Uses pandas for parsing so both .csv and .xlsx are supported.

    Expected columns for Students:
      full_name, student_id, email, username, password (optional),
      department_code, semester, batch_year, gender, phone

    Expected columns for Faculty:
      full_name, faculty_id, email, username, password (optional),
      department_code, designation, qualification, specialization, phone
    """
    results = None
    import_type = request.args.get("type", "students")  # students | faculty

    if request.method == "POST":
        import_type = request.form.get("import_type", "students")
        file = request.files.get("import_file")

        if not file or not file.filename:
            flash("Please select a file to import.", "warning")
            return render_template("admin/bulk_import.html",
                                   title="Bulk Import", results=None, import_type=import_type)

        filename = secure_filename(file.filename)
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext not in ("csv", "xlsx"):
            flash("Only CSV (.csv) and Excel (.xlsx) files are supported.", "warning")
            return render_template("admin/bulk_import.html",
                                   title="Bulk Import", results=None, import_type=import_type)

        # Save temp file
        import_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], "imports")
        os.makedirs(import_dir, exist_ok=True)
        filepath = os.path.join(import_dir, filename)
        file.save(filepath)

        try:
            import pandas as pd
            if ext == "csv":
                df = pd.read_csv(filepath, encoding="utf-8-sig", dtype=str)
            else:
                df = pd.read_excel(filepath, dtype=str)
            df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
        except ImportError:
            flash("pandas is not installed. Run: pip install pandas>=2.0.0 openpyxl>=3.1.0", "danger")
            return redirect(url_for("admin.bulk_import"))
        except Exception as e:
            flash(f"Could not read file: {e}", "danger")
            return redirect(url_for("admin.bulk_import"))

        success, errors = 0, []

        if import_type == "students":
            required = {"full_name", "student_id", "email", "username"}
            if not required.issubset(set(df.columns)):
                missing = required - set(df.columns)
                flash(f"Missing required columns: {', '.join(missing)}", "danger")
                return render_template("admin/bulk_import.html",
                                       title="Bulk Import", results=None, import_type=import_type)

            for i, row in df.iterrows():
                row_num = i + 2
                try:
                    uname = str(row.get("username", "")).strip()
                    email = str(row.get("email", "")).strip()
                    sid   = str(row.get("student_id", "")).strip()
                    fname = str(row.get("full_name", "")).strip()
                    dept_code = str(row.get("department_code", "")).strip().upper()

                    if not all([uname, email, sid, fname]):
                        errors.append(f"Row {row_num}: Missing required field(s).")
                        continue

                    if User.query.filter_by(username=uname).first():
                        errors.append(f"Row {row_num}: Username '{uname}' already exists.")
                        continue
                    if User.query.filter_by(email=email).first():
                        errors.append(f"Row {row_num}: Email '{email}' already exists.")
                        continue
                    if Student.query.filter_by(student_id=sid).first():
                        errors.append(f"Row {row_num}: Student ID '{sid}' already exists.")
                        continue

                    dept = Department.query.filter_by(code=dept_code).first() if dept_code else None

                    user = User(username=uname, email=email, role=RoleEnum.STUDENT)
                    pwd  = str(row.get("password", "")).strip() or sid
                    user.set_password(pwd)
                    db.session.add(user)
                    db.session.flush()

                    student = Student(
                        user_id=user.id,
                        student_id=sid,
                        full_name=fname,
                        gender=str(row.get("gender", "")).strip() or None,
                        phone=str(row.get("phone", "")).strip() or None,
                        department_id=dept.id if dept else None,
                        current_semester=int(row.get("semester", 1) or 1),
                        batch_year=int(row.get("batch_year", datetime.utcnow().year) or datetime.utcnow().year),
                        is_active=True
                    )
                    db.session.add(student)
                    success += 1
                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)[:100]}")

        elif import_type == "faculty":
            required = {"full_name", "faculty_id", "email", "username"}
            if not required.issubset(set(df.columns)):
                missing = required - set(df.columns)
                flash(f"Missing required columns: {', '.join(missing)}", "danger")
                return render_template("admin/bulk_import.html",
                                       title="Bulk Import", results=None, import_type=import_type)

            for i, row in df.iterrows():
                row_num = i + 2
                try:
                    uname = str(row.get("username", "")).strip()
                    email = str(row.get("email", "")).strip()
                    fid   = str(row.get("faculty_id", "")).strip()
                    fname = str(row.get("full_name", "")).strip()
                    dept_code = str(row.get("department_code", "")).strip().upper()

                    if not all([uname, email, fid, fname]):
                        errors.append(f"Row {row_num}: Missing required field(s).")
                        continue

                    if User.query.filter_by(username=uname).first():
                        errors.append(f"Row {row_num}: Username '{uname}' already exists.")
                        continue
                    if Faculty.query.filter_by(faculty_id=fid).first():
                        errors.append(f"Row {row_num}: Faculty ID '{fid}' already exists.")
                        continue

                    dept = Department.query.filter_by(code=dept_code).first() if dept_code else None

                    user = User(username=uname, email=email, role=RoleEnum.FACULTY)
                    pwd  = str(row.get("password", "")).strip() or fid
                    user.set_password(pwd)
                    db.session.add(user)
                    db.session.flush()

                    faculty_obj = Faculty(
                        user_id=user.id,
                        faculty_id=fid,
                        full_name=fname,
                        designation=str(row.get("designation", "")).strip() or None,
                        qualification=str(row.get("qualification", "")).strip() or None,
                        phone=str(row.get("phone", "")).strip() or None,
                        specialization=str(row.get("specialization", "")).strip() or None,
                        department_id=dept.id if dept else None,
                        is_active=True
                    )
                    db.session.add(faculty_obj)
                    success += 1
                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)[:100]}")

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"Database error during import: {e}", "danger")
            return redirect(url_for("admin.bulk_import"))

        results = {"success": success, "errors": errors, "import_type": import_type}
        flash(f"Import complete: {success} {import_type} imported, {len(errors)} error(s).", "info")

    return render_template("admin/bulk_import.html",
                           title="Bulk Import", results=results, import_type=import_type)


@admin_bp.route("/import/template/<import_type>")
@login_required
@admin_required
def download_import_template(import_type):
    """Download a CSV template file for bulk import."""
    import csv as _csv
    import io as _io
    from flask import Response

    templates = {
        "students": [
            "full_name,student_id,email,username,password,department_code,semester,batch_year,gender,phone",
            "John Smith,STU002,john@example.com,john_smith,,CS,1,2024,male,9876543210",
            "Jane Doe,STU003,jane@example.com,jane_doe,,CS,2,2023,female,9876543211",
        ],
        "faculty": [
            "full_name,faculty_id,email,username,password,department_code,designation,qualification,specialization,phone",
            "Dr. Alice Brown,FAC002,alice@example.com,alice_brown,,CS,Assistant Professor,Ph.D. Computer Science,Machine Learning,9876543212",
        ],
    }

    if import_type not in templates:
        flash("Invalid template type.", "warning")
        return redirect(url_for("admin.bulk_import"))

    csv_content = "\n".join(templates[import_type])
    filename = f"import_template_{import_type}.csv"
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
