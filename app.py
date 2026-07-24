"""
app.py – EduGuard AI Application Factory
==========================================
Creates and configures the Flask application.
All extensions and blueprints are initialised here.
"""

from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import get_config
from database import init_db, db
from models import User
from email_service import init_mail

# Module-level CSRFProtect instance so it can be imported by tests if needed
csrf = CSRFProtect()


def create_app(config_class=None) -> Flask:
    """
    Application factory pattern.
    Call this to create and configure a Flask app instance.
    """
    app = Flask(__name__)

    # ── Load configuration ────────────────────────────────────────────────────
    cfg = config_class or get_config()
    app.config.from_object(cfg)

    # ── CSRF Protection ───────────────────────────────────────────────────────
    csrf.init_app(app)

    # ── Initialise database ───────────────────────────────────────────────────
    init_db(app)

    # ── Flask-Mail (email alerts) ─────────────────────────────────────────────
    init_mail(app)

    # ── Flask-Login ───────────────────────────────────────────────────────────
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id: str):
        return User.query.get(int(user_id))

    # ── Register Blueprints ───────────────────────────────────────────────────
    from routes import main_bp
    from blueprints.auth.routes import auth_bp
    from blueprints.admin.routes import admin_bp
    from blueprints.faculty.routes import faculty_bp
    from blueprints.student.routes import student_bp
    from blueprints.ai.routes import ai_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(faculty_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(ai_bp)

    # ── Jinja2 Global Utilities ───────────────────────────────────────────────
    from datetime import datetime

    @app.template_filter("datefmt")
    def datefmt(value, fmt="%d %b %Y"):
        if not value:
            return "—"
        if isinstance(value, str):
            try:
                value = datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                return value
        return value.strftime(fmt)

    @app.template_filter("timefmt")
    def timefmt(value, fmt="%H:%M"):
        if not value:
            return "—"
        return value.strftime(fmt)

    @app.context_processor
    def inject_globals():
        return {"app_name": "EduGuard AI", "current_year": datetime.utcnow().year}

    # ── CLI: diagnose-ai ──────────────────────────────────────────────────────
    @app.cli.command("diagnose-ai")
    def diagnose_ai():
        """
        Run IBM watsonx.ai connectivity diagnostics.
        Usage: flask diagnose-ai
        Checks: .env loading, API key, Project ID, IAM token, account state,
                model catalogue, direct REST generation, and full SDK generate.
        """
        from ai_service import run_diagnostics
        import os as _os

        print("\n" + "=" * 60)
        print("  EduGuard AI -- IBM watsonx.ai Diagnostics")
        print("=" * 60)

        # Show current config
        cur_model = _os.environ.get("WATSONX_MODEL_ID", "(not set)")
        cur_url   = _os.environ.get("WATSONX_URL",   "(not set)")
        print(f"  URL       : {cur_url}")
        print(f"  Model     : {cur_model}")
        print()

        result = run_diagnostics()

        checks = [
            ("env_loaded",       ".env file loaded"),
            ("api_key_set",      "WATSONX_API_KEY is set (not placeholder)"),
            ("project_id_set",   "WATSONX_PROJECT_ID is set (not placeholder)"),
            ("iam_token",        "IBM Cloud IAM token obtained"),
            ("sdk_init",         "IBM SDK APIClient + ModelInference created"),
            ("sdk_generate",     "generate_text() returned a response"),
        ]

        for key, label in checks:
            status = "PASS" if result.get(key) else "FAIL"
            print(f"  [{status}]  {label}")

        # Account info
        if result.get("account_id"):
            print(f"\n  IBM Account ID : {result['account_id']}")

        if result.get("account_frozen"):
            print("  [WARN] ACCOUNT FROZEN – Llama 3.3 still works on frozen accounts.")
            print("         Other models may be restricted.  Upgrade at https://cloud.ibm.com/")

        # Direct REST result
        if result.get("direct_rest_status"):
            st  = result["direct_rest_status"]
            txt = result.get("direct_rest_text", "")
            if st == 200:
                print(f"\n  Direct REST    : HTTP {st} -> '{txt[:60]}'")
            else:
                print(f"\n  Direct REST    : HTTP {st} (failed)")

        # Available models in this region
        available = result.get("available_models", [])
        if available:
            print(f"\n  Available text-generation models in this region ({len(available)}):")
            for mid in available:
                marker = " <-- CURRENT" if mid == cur_model else ""
                print(f"    {mid}{marker}")
        else:
            print("\n  [WARN] Could not retrieve model catalogue.")

        recommended = result.get("recommended_model")
        if recommended and recommended != cur_model:
            print(f"\n  [HINT] Recommended model for this region: {recommended}")
            print(f"         Current model in .env: {cur_model}")
            print(f"         Update WATSONX_MODEL_ID={recommended} in .env")

        # Errors
        if result.get("errors"):
            print("\n  ERRORS:")
            for err in result["errors"]:
                print(f"    - {err[:120]}")

        # Final verdict
        print()
        if result.get("sdk_generate"):
            print("  [OK] generate_text() is working correctly!")
            print(f"  [OK] Model '{cur_model}' is live in this region.")
            print("  [OK] All AI features (chatbot, analysis, reports) are active.\n")
        else:
            print("  [FAIL] generate_text() did not succeed.")
            if available and cur_model not in available:
                print(f"  [REASON] Model '{cur_model}' is NOT in the available catalogue.")
                if recommended:
                    print(f"  [FIX]    Set WATSONX_MODEL_ID={recommended} in .env")
            elif result.get("account_frozen"):
                print("  [REASON] Account frozen – but Llama 3.3 should still work.")
                print("  [FIX]    Ensure WATSONX_MODEL_ID=meta-llama/llama-3-3-70b-instruct")
            else:
                print("  [FIX] Check .env credentials and run flask diagnose-ai again.\n")

    # ── CLI: seed admin ───────────────────────────────────────────────────────
    @app.cli.command("seed-admin")
    def seed_admin():
        """Create default admin user. Run: flask seed-admin"""
        from models import RoleEnum
        if not User.query.filter_by(role=RoleEnum.ADMIN).first():
            admin = User(username="admin", email="admin@eduguard.ai", role=RoleEnum.ADMIN)
            admin.set_password("Admin@123")
            db.session.add(admin)
            db.session.commit()
            print("Admin user created: admin / Admin@123")
        else:
            print("Admin user already exists.")

    # ── CLI: seed demo data (faculty + student + dept + subjects) ─────────────
    @app.cli.command("seed-demo")
    def seed_demo():
        """
        Create demo Department, Subjects, Units, Faculty and Student accounts.
        Run: flask seed-demo
        Credentials created:
          Faculty  -> username: faculty1   password: Faculty@123
          Student  -> username: student1   password: Student@123
        """
        from models import (RoleEnum, Department, Subject, Unit,
                            Faculty, Student, FacultySubject)

        # ── Department ────────────────────────────────────────────────────────
        dept = Department.query.filter_by(code="CS").first()
        if not dept:
            dept = Department(name="Computer Science", code="CS",
                              description="Computer Science & Engineering")
            db.session.add(dept)
            db.session.flush()
            print("Department created: Computer Science (CS)")
        else:
            print("Department CS already exists.")

        # ── Subjects ──────────────────────────────────────────────────────────
        sub1 = Subject.query.filter_by(code="CS101").first()
        if not sub1:
            sub1 = Subject(name="Data Structures", code="CS101",
                           credits=4, semester=1, department_id=dept.id)
            db.session.add(sub1)
            db.session.flush()
            # Units for CS101
            for n, name in [(1, "Arrays & Linked Lists"), (2, "Stacks & Queues"),
                            (3, "Trees"), (4, "Graphs")]:
                db.session.add(Unit(name=name, unit_number=n, subject_id=sub1.id))
            print("Subject created: Data Structures (CS101) with 4 units")
        else:
            print("Subject CS101 already exists.")

        sub2 = Subject.query.filter_by(code="CS102").first()
        if not sub2:
            sub2 = Subject(name="Python Programming", code="CS102",
                           credits=3, semester=1, department_id=dept.id)
            db.session.add(sub2)
            db.session.flush()
            for n, name in [(1, "Basics & Syntax"), (2, "Functions & Modules"),
                            (3, "OOP"), (4, "File Handling")]:
                db.session.add(Unit(name=name, unit_number=n, subject_id=sub2.id))
            print("Subject created: Python Programming (CS102) with 4 units")
        else:
            print("Subject CS102 already exists.")

        db.session.flush()

        # ── Faculty user + profile + subject assignments ──────────────────────
        fac_user = User.query.filter_by(username="faculty1").first()
        if not fac_user:
            fac_user = User(username="faculty1",
                            email="faculty1@eduguard.ai",
                            role=RoleEnum.FACULTY)
            fac_user.set_password("Faculty@123")
            db.session.add(fac_user)
            db.session.flush()

            faculty = Faculty(
                user_id=fac_user.id,
                faculty_id="FAC001",
                full_name="Dr. Sarah Johnson",
                designation="Assistant Professor",
                qualification="Ph.D. Computer Science",
                department_id=dept.id,
                specialization="Data Structures & Algorithms"
            )
            db.session.add(faculty)
            db.session.flush()

            # Assign both subjects to this faculty
            for subj in [sub1, sub2]:
                if not FacultySubject.query.filter_by(
                        faculty_id=faculty.id, subject_id=subj.id).first():
                    db.session.add(FacultySubject(
                        faculty_id=faculty.id, subject_id=subj.id))

            db.session.commit()
            print("Faculty created:  faculty1 / Faculty@123  (Dr. Sarah Johnson)")
        else:
            print("Faculty user faculty1 already exists.")

        # ── Student user + profile ────────────────────────────────────────────
        stu_user = User.query.filter_by(username="student1").first()
        if not stu_user:
            stu_user = User(username="student1",
                            email="student1@eduguard.ai",
                            role=RoleEnum.STUDENT)
            stu_user.set_password("Student@123")
            db.session.add(stu_user)
            db.session.flush()

            student = Student(
                user_id=stu_user.id,
                student_id="STU001",
                full_name="Alex Thompson",
                gender="male",
                department_id=dept.id,
                current_semester=1,
                batch_year=2024
            )
            db.session.add(student)
            db.session.commit()
            print("Student created:  student1 / Student@123  (Alex Thompson)")
        else:
            print("Student user student1 already exists.")

        print("\nDemo seed complete.")
        print("  Admin   -> admin    / Admin@123")
        print("  Faculty -> faculty1 / Faculty@123")
        print("  Student -> student1 / Student@123")

    return app


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=5000)
