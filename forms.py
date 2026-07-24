"""
forms.py – EduGuard AI WTForms Form Definitions
=================================================
Centralised form definitions using Flask-WTF and WTForms.
All forms are validated server-side.
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, PasswordField, EmailField, SelectField,
    TextAreaField, IntegerField, FloatField, DateField, TimeField,
    BooleanField, HiddenField, SubmitField
)
from wtforms.validators import (
    DataRequired, Email, Length, EqualTo, Optional,
    NumberRange, ValidationError
)


# ─────────────────────────────────────────────────────────────────────────────
# AUTH FORMS
# ─────────────────────────────────────────────────────────────────────────────

class LoginForm(FlaskForm):
    """Universal login form for all roles."""
    username = StringField("Username / Email",
                           validators=[DataRequired(), Length(min=3, max=120)])
    password = PasswordField("Password",
                             validators=[DataRequired(), Length(min=6)])
    remember_me = BooleanField("Remember Me")
    submit = SubmitField("Login")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current Password", validators=[DataRequired()])
    new_password = PasswordField("New Password",
                                 validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField("Confirm Password",
                                     validators=[DataRequired(), EqualTo("new_password")])
    submit = SubmitField("Change Password")


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN – DEPARTMENT
# ─────────────────────────────────────────────────────────────────────────────

class DepartmentForm(FlaskForm):
    name = StringField("Department Name",
                       validators=[DataRequired(), Length(max=120)])
    code = StringField("Department Code",
                       validators=[DataRequired(), Length(max=20)])
    description = TextAreaField("Description", validators=[Optional(), Length(max=500)])
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save Department")


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN – SUBJECT
# ─────────────────────────────────────────────────────────────────────────────

class SubjectForm(FlaskForm):
    name = StringField("Subject Name",
                       validators=[DataRequired(), Length(max=120)])
    code = StringField("Subject Code",
                       validators=[DataRequired(), Length(max=20)])
    credits = IntegerField("Credits", validators=[DataRequired(), NumberRange(min=1, max=10)], default=3)
    semester = IntegerField("Semester", validators=[Optional(), NumberRange(min=1, max=12)])
    description = TextAreaField("Description", validators=[Optional(), Length(max=500)])
    department_id = SelectField("Department", coerce=int, validators=[DataRequired()])
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save Subject")


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN – UNIT
# ─────────────────────────────────────────────────────────────────────────────

class UnitForm(FlaskForm):
    name = StringField("Unit Name",
                       validators=[DataRequired(), Length(max=150)])
    unit_number = IntegerField("Unit Number",
                               validators=[DataRequired(), NumberRange(min=1)])
    description = TextAreaField("Description", validators=[Optional(), Length(max=500)])
    subject_id = SelectField("Subject", coerce=int, validators=[DataRequired()])
    submit = SubmitField("Save Unit")


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN – STUDENT
# ─────────────────────────────────────────────────────────────────────────────

class StudentForm(FlaskForm):
    full_name = StringField("Full Name",
                            validators=[DataRequired(), Length(max=150)])
    student_id = StringField("Enrollment / Student ID",
                             validators=[DataRequired(), Length(max=30)])
    email = EmailField("Email", validators=[DataRequired(), Email()])
    username = StringField("Username",
                           validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField("Password",
                             validators=[Optional(), Length(min=6)])
    date_of_birth = DateField("Date of Birth", validators=[Optional()])
    gender = SelectField("Gender",
                         choices=[("", "Select"), ("male", "Male"), ("female", "Female"), ("other", "Other")],
                         validators=[Optional()])
    phone = StringField("Phone", validators=[Optional(), Length(max=20)])
    address = TextAreaField("Address", validators=[Optional()])
    department_id = SelectField("Department", coerce=int, validators=[Optional()])
    current_semester = IntegerField("Current Semester",
                                    validators=[Optional(), NumberRange(min=1, max=12)], default=1)
    batch_year = IntegerField("Batch Year", validators=[Optional(), NumberRange(min=2000, max=2100)])
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save Student")


class StudentCSVUploadForm(FlaskForm):
    csv_file = FileField("CSV File",
                         validators=[DataRequired(), FileAllowed(["csv"], "CSV files only!")])
    submit = SubmitField("Upload Students")


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN – FACULTY
# ─────────────────────────────────────────────────────────────────────────────

class FacultyForm(FlaskForm):
    full_name = StringField("Full Name",
                            validators=[DataRequired(), Length(max=150)])
    faculty_id = StringField("Faculty ID",
                             validators=[DataRequired(), Length(max=30)])
    email = EmailField("Email", validators=[DataRequired(), Email()])
    username = StringField("Username",
                           validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField("Password", validators=[Optional(), Length(min=6)])
    designation = StringField("Designation", validators=[Optional(), Length(max=100)])
    qualification = StringField("Qualification", validators=[Optional(), Length(max=200)])
    phone = StringField("Phone", validators=[Optional(), Length(max=20)])
    department_id = SelectField("Department", coerce=int, validators=[Optional()])
    specialization = StringField("Specialization", validators=[Optional(), Length(max=200)])
    joining_date = DateField("Joining Date", validators=[Optional()])
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save Faculty")


# ─────────────────────────────────────────────────────────────────────────────
# FACULTY – ATTENDANCE
# ─────────────────────────────────────────────────────────────────────────────

class AttendanceForm(FlaskForm):
    subject_id = SelectField("Subject", coerce=int, validators=[DataRequired()])
    date = DateField("Date", validators=[DataRequired()])
    submit = SubmitField("Mark Attendance")


# ─────────────────────────────────────────────────────────────────────────────
# FACULTY – ASSIGNMENT MARKS
# ─────────────────────────────────────────────────────────────────────────────

class AssignmentForm(FlaskForm):
    student_id = SelectField("Student", coerce=int, validators=[DataRequired()])
    subject_id = SelectField("Subject", coerce=int, validators=[DataRequired()])
    title = StringField("Assignment Title",
                        validators=[DataRequired(), Length(max=200)])
    max_marks = FloatField("Maximum Marks",
                           validators=[DataRequired(), NumberRange(min=1)], default=100.0)
    obtained_marks = FloatField("Marks Obtained",
                                validators=[DataRequired(), NumberRange(min=0)])
    submission_date = DateField("Submission Date", validators=[Optional()])
    remarks = TextAreaField("Remarks", validators=[Optional()])
    submit = SubmitField("Save Assignment")


# ─────────────────────────────────────────────────────────────────────────────
# FACULTY – FEEDBACK
# ─────────────────────────────────────────────────────────────────────────────

RATING_CHOICES = [(1, "1 – Poor"), (2, "2 – Below Average"),
                  (3, "3 – Average"), (4, "4 – Good"), (5, "5 – Excellent")]


class FacultyFeedbackForm(FlaskForm):
    student_id = SelectField("Student", coerce=int, validators=[DataRequired()])
    subject_id = SelectField("Subject", coerce=int, validators=[Optional()])
    class_participation = SelectField("Class Participation", coerce=int,
                                      choices=RATING_CHOICES, validators=[DataRequired()])
    subject_understanding = SelectField("Subject Understanding", coerce=int,
                                        choices=RATING_CHOICES, validators=[DataRequired()])
    assignment_quality = SelectField("Assignment Quality", coerce=int,
                                     choices=RATING_CHOICES, validators=[DataRequired()])
    learning_progress = SelectField("Learning Progress", coerce=int,
                                    choices=RATING_CHOICES, validators=[DataRequired()])
    comments = TextAreaField("Comments", validators=[Optional(), Length(max=1000)])
    feedback_date = DateField("Feedback Date", validators=[Optional()])
    submit = SubmitField("Submit Feedback")


# ─────────────────────────────────────────────────────────────────────────────
# FACULTY – QUESTION BANK
# ─────────────────────────────────────────────────────────────────────────────

class QuestionForm(FlaskForm):
    subject_id = SelectField("Subject", coerce=int, validators=[DataRequired()])
    unit_id = SelectField("Unit", coerce=int, validators=[DataRequired()])
    question_type = SelectField("Question Type",
                                choices=[("mcq", "Multiple Choice"), ("true_false", "True / False"), ("fill_blank", "Fill in the Blank")],
                                validators=[DataRequired()])
    difficulty = SelectField("Difficulty",
                             choices=[("easy", "Easy"), ("medium", "Medium"), ("hard", "Hard")],
                             validators=[DataRequired()])
    question_text = TextAreaField("Question",
                                  validators=[DataRequired(), Length(max=2000)])
    option_a = StringField("Option A", validators=[Optional(), Length(max=255)])
    option_b = StringField("Option B", validators=[Optional(), Length(max=255)])
    option_c = StringField("Option C", validators=[Optional(), Length(max=255)])
    option_d = StringField("Option D", validators=[Optional(), Length(max=255)])
    correct_answer = StringField("Correct Answer",
                                 validators=[DataRequired(), Length(max=255)])
    explanation = TextAreaField("Explanation", validators=[Optional(), Length(max=1000)])
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save Question")


# ─────────────────────────────────────────────────────────────────────────────
# FACULTY – ASSESSMENT SCHEDULER
# ─────────────────────────────────────────────────────────────────────────────

class AssessmentForm(FlaskForm):
    title = StringField("Assessment Title",
                        validators=[DataRequired(), Length(max=200)])
    subject_id = SelectField("Subject", coerce=int, validators=[DataRequired()])
    unit_id = SelectField("Unit", coerce=int, validators=[Optional()])
    scheduled_date = DateField("Scheduled Date", validators=[DataRequired()])
    start_time = TimeField("Start Time", validators=[Optional()])
    duration_minutes = IntegerField("Duration (minutes)",
                                    validators=[DataRequired(), NumberRange(min=5, max=300)], default=30)
    total_questions = IntegerField("Total Questions",
                                   validators=[DataRequired(), NumberRange(min=1, max=100)], default=10)
    easy_count = IntegerField("Easy Questions",
                              validators=[DataRequired(), NumberRange(min=0)], default=4)
    medium_count = IntegerField("Medium Questions",
                                validators=[DataRequired(), NumberRange(min=0)], default=4)
    hard_count = IntegerField("Hard Questions",
                              validators=[DataRequired(), NumberRange(min=0)], default=2)
    max_marks = FloatField("Maximum Marks",
                           validators=[DataRequired(), NumberRange(min=1)], default=10.0)
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Schedule Assessment")

    def validate_total_questions(self, field):
        easy = self.easy_count.data or 0
        medium = self.medium_count.data or 0
        hard = self.hard_count.data or 0
        if (easy + medium + hard) != field.data:
            raise ValidationError("Easy + Medium + Hard must equal Total Questions.")


# ─────────────────────────────────────────────────────────────────────────────
# STUDENT – ACADEMIC RECORD
# ─────────────────────────────────────────────────────────────────────────────

class AcademicRecordForm(FlaskForm):
    semester = IntegerField("Semester",
                            validators=[DataRequired(), NumberRange(min=1, max=12)])
    academic_year = StringField("Academic Year",
                                validators=[Optional(), Length(max=20)])
    gpa = FloatField("GPA", validators=[DataRequired(), NumberRange(min=0, max=10)])
    sgpa = FloatField("SGPA", validators=[Optional(), NumberRange(min=0, max=10)])
    cgpa = FloatField("CGPA", validators=[Optional(), NumberRange(min=0, max=10)])
    total_credits = IntegerField("Total Credits", validators=[Optional(), NumberRange(min=0)])
    earned_credits = IntegerField("Earned Credits", validators=[Optional(), NumberRange(min=0)])
    backlogs = IntegerField("Backlogs",
                            validators=[Optional(), NumberRange(min=0)], default=0)
    remarks = TextAreaField("Remarks", validators=[Optional()])
    submit = SubmitField("Save Record")
