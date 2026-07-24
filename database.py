"""
database.py – EduGuard AI Database Initialisation
==================================================
Provides the shared SQLAlchemy instance and helper utilities.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# ── Shared SQLAlchemy instance (imported by models and app) ──────────────────
db: SQLAlchemy = SQLAlchemy()
migrate: Migrate = Migrate()


def init_db(app) -> None:
    """
    Bind the SQLAlchemy instance to the Flask app and create all tables.
    Called once during application factory setup.
    """
    db.init_app(app)
    migrate.init_app(app, db)

    with app.app_context():
        # Import all models so SQLAlchemy is aware of them before create_all
        import models  # noqa: F401
        db.create_all()
