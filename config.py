"""
config.py – EduGuard AI Configuration Module
=============================================
Centralised application configuration loaded from environment variables.
Designed to be extended for Phase 2 (AI / Email / Watsonx integration).
"""

import os
from dotenv import load_dotenv
from urllib.parse import quote_plus

# Load .env file if present
load_dotenv()


class Config:
    """Base configuration shared by all environments."""

    # ── Flask ────────────────────────────────────────────────────────────────
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-fallback-secret-key-change-me")
    FLASK_ENV: str = os.environ.get("FLASK_ENV", "development")

    # ── Database ─────────────────────────────────────────────────────────────
    DB_HOST: str = os.environ.get("DB_HOST", "localhost")
    DB_PORT: str = os.environ.get("DB_PORT", "3306")
    DB_USER: str = os.environ.get("DB_USER", "root")
    DB_PASSWORD: str = os.environ.get("DB_PASSWORD", "")
    DB_NAME: str = os.environ.get("DB_NAME", "eduguard_ai")

    SQLALCHEMY_DATABASE_URI = (
    f"mysql+pymysql://{DB_USER}:{quote_plus(DB_PASSWORD or '')}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
 )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    SQLALCHEMY_ECHO: bool = False  # Set True to log SQL queries during development

    # ── File Uploads ─────────────────────────────────────────────────────────
    UPLOAD_FOLDER: str = os.environ.get("UPLOAD_FOLDER", "uploads")
    MAX_CONTENT_LENGTH: int = int(os.environ.get("MAX_CONTENT_LENGTH", 16 * 1024 * 1024))
    ALLOWED_EXTENSIONS: set = {"csv", "xlsx", "pdf", "png", "jpg", "jpeg"}

    # ── Session / Login ───────────────────────────────────────────────────────
    REMEMBER_COOKIE_DURATION: int = 86400 * 7   # 7 days
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"

    # ── Pagination ────────────────────────────────────────────────────────────
    ITEMS_PER_PAGE: int = 15

    # ── AI / IBM watsonx.ai ───────────────────────────────────────────────────
    WATSONX_API_KEY: str = os.environ.get("WATSONX_API_KEY", "")
    WATSONX_PROJECT_ID: str = os.environ.get("WATSONX_PROJECT_ID", "")
    WATSONX_URL: str = os.environ.get("WATSONX_URL", "https://au-syd.ml.cloud.ibm.com")
    # Default model for the au-syd region.
    # ibm/granite-3-8b-instruct and ibm/granite-13b-instruct-v2 are NOT available
    # in au-syd.  meta-llama/llama-3-3-70b-instruct is the confirmed working
    # text-generation model in this region as of 2025.
    WATSONX_MODEL_ID: str = os.environ.get("WATSONX_MODEL_ID", "meta-llama/llama-3-3-70b-instruct")

    # ── AI Agent Instructions (configurable without code changes) ─────────────
    AI_RESPONSE_LANGUAGE: str = os.environ.get("AI_RESPONSE_LANGUAGE", "English")
    AI_RESPONSE_STYLE: str = os.environ.get("AI_RESPONSE_STYLE", "detailed")
    AI_EDUCATION_CONTEXT: str = os.environ.get("AI_EDUCATION_CONTEXT", "undergraduate")
    AI_MAX_TOKENS: int = int(os.environ.get("AI_MAX_TOKENS", 1500))
    AI_TEMPERATURE: float = float(os.environ.get("AI_TEMPERATURE", 0.7))
    AI_SAFETY_LEVEL: str = os.environ.get("AI_SAFETY_LEVEL", "strict")
    AI_CUSTOM_POLICY: str = os.environ.get("AI_CUSTOM_POLICY", "")

    # AGENT_INSTRUCTIONS – injected into every AI prompt as a system directive.
    # Customise academic policy, response tone, language, safety rules and
    # recommendation style entirely from the .env file.
    @classmethod
    def get_agent_instructions(cls) -> str:
        """Build the AGENT_INSTRUCTIONS block from individual env variables."""
        custom = cls.AI_CUSTOM_POLICY.strip()
        policy_line = f"\nInstitutional Policy: {custom}" if custom else ""
        return (
            f"You are EduGuard AI, an intelligent academic advisor for {cls.AI_EDUCATION_CONTEXT} "
            f"students. Always respond in {cls.AI_RESPONSE_LANGUAGE} using a {cls.AI_RESPONSE_STYLE} style. "
            f"Safety level: {cls.AI_SAFETY_LEVEL} — keep all responses educational, safe, and professional. "
            f"Never discuss harmful, political, or non-academic topics. "
            f"Focus exclusively on academic performance, study strategies, and student well-being.{policy_line}"
        )

    # ── Email Alerts (Phase 2 – placeholder) ─────────────────────────────────
    MAIL_SERVER: str = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT: int = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS: bool = os.environ.get("MAIL_USE_TLS", "True") == "True"
    MAIL_USERNAME: str = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD: str = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER: str = os.environ.get("MAIL_DEFAULT_SENDER", "")


class DevelopmentConfig(Config):
    """Development-specific overrides."""
    DEBUG: bool = True
    SQLALCHEMY_ECHO: bool = False


class ProductionConfig(Config):
    """Production-specific overrides."""
    DEBUG: bool = False
    SESSION_COOKIE_SECURE: bool = True  # Requires HTTPS


class TestingConfig(Config):
    """Testing overrides."""
    TESTING: bool = True
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///:memory:"
    WTF_CSRF_ENABLED: bool = False


# ── Config selector ──────────────────────────────────────────────────────────
config_map: dict = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config() -> Config:
    """Return the correct config class based on FLASK_ENV."""
    env = os.environ.get("FLASK_ENV", "development").lower()
    return config_map.get(env, DevelopmentConfig)
