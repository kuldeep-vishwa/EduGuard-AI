"""
database.py – EduGuard AI Database Initialisation
==================================================
Provides the shared SQLAlchemy instance and helper utilities.
"""

import os
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
        
        # Skip heavy table creation on Vercel to prevent serverless timeouts
        if not os.getenv('VERCEL'):
            try:
                db.create_all()
            except Exception as e:
                print(f"Local DB initialization note: {e}")