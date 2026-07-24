"""
ai_service.py – EduGuard AI  ·  IBM watsonx.ai Granite Integration
====================================================================
Single, modular AI service layer.  All IBM Granite calls, Academic
Health Score calculations, and prompt-building logic live here so
that routes and templates stay clean.

Architecture is deliberately ML-model-agnostic: replace the
`_call_granite` helper (or swap in the `health_score_calculator`
function) to move to Random Forest / XGBoost without touching any
other file.

Sections
--------
1. IBM watsonx.ai client bootstrap  (with full debug logging)
2. AGENT_INSTRUCTIONS builder       (driven by .env config)
3. Academic Health Score            (rule-based, configurable weights)
4. Prompt builders                  (assessment analysis, risk analysis, chatbot)
5. Public API functions             (called by blueprints)
6. Text parsers & fallback generators

ROOT CAUSE FIXES APPLIED
-------------------------
Fix 1 – validate=False in ModelInference constructor.
        SDK 1.6.0 default validate=True fires a Watson Studio profile-check
        network call at __init__ time.  If the IBM Cloud account has not
        completed Watson Studio registration (or the project belongs to a
        different account) this raises CannotSetProjectOrSpace/401 before
        any generation is attempted.  Setting validate=False defers all
        auth checks to the actual generate_text() call, where we can catch
        and surface the real error.

Fix 2 – scope_validation=False in APIClient.
        APIClient calls set.default_project() which internally POSTs to the
        Watson Studio user-profile endpoint.  scope_validation=False skips
        that check and lets the SDK proceed to generation. Auth errors are
        then returned as 403 ApiRequestFailure on the actual call.

Fix 3 – Persistent failure caching removed.
        Added _wx_init_failed flag + retry window so that after credentials
        are corrected the model is re-initialised without restarting Flask.

Fix 4 – MIN_NEW_TOKENS reduced to 1.
        min_new_tokens=50 caused silent truncation failures on short chatbot
        prompts where the model naturally produces fewer than 50 tokens.

Fix 5 – TextGenParameters dataclass instead of metanames dict.
        Using the typed TextGenParameters class is the SDK 1.6.0 recommended
        approach and avoids dict-key mismatch issues from older metanames
        mappings.

Fix 6 – Default model updated to meta-llama/llama-3-3-70b-instruct.
        ibm/granite-13b-instruct-v2 is deprecated everywhere.
        ibm/granite-3-8b-instruct does NOT exist in the au-syd region.
        meta-llama/llama-3-3-70b-instruct is the confirmed working
        text-generation model in au-syd (tested 2025, ibm-watsonx-ai 1.6.0).
        The Llama 3.3 model is hosted by IBM on watsonx.ai infrastructure
        and supports the same generate_text() SDK call as Granite models.

Fix 8 – URL default corrected from us-south to au-syd.
        The hardcoded fallback URL in _get_watsonx_model() previously fell
        back to https://us-south.ml.cloud.ibm.com which is the wrong region
        for this account.  All region-specific defaults now use au-syd.

Fix 7 – Full console debug logging added.
        A dedicated StreamHandler is attached to the module logger at INFO
        level so that auth steps, prompts sent, and errors are always visible
        in the Flask development console regardless of Flask's log level.
"""

import json
import logging
import warnings
from datetime import datetime, timedelta
from typing import Optional

# ── Dedicated console logger (always visible in Flask dev server) ─────────────
logger = logging.getLogger("eduguard.ai_service")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setLevel(logging.DEBUG)
    _handler.setFormatter(logging.Formatter(
        "[EduGuard AI] %(levelname)s – %(message)s"
    ))
    logger.addHandler(_handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # prevent double-printing via root logger


# ─────────────────────────────────────────────────────────────────────────────
# 1.  IBM watsonx.ai Client Bootstrap
# ─────────────────────────────────────────────────────────────────────────────

_wx_model       = None   # cached ModelInference instance (None = not yet init)
_wx_init_failed = False  # True after a failed init attempt
_wx_retry_after = None   # datetime after which we will retry initialisation


def _reset_model_cache():
    """Force the next call to re-initialise the watsonx.ai model."""
    global _wx_model, _wx_init_failed, _wx_retry_after
    _wx_model       = None
    _wx_init_failed = False
    _wx_retry_after = None


def _get_watsonx_model():
    """
    Return a cached ibm-watsonx-ai ModelInference instance.

    Initialisation is lazy (first call) and retried every 5 minutes after a
    failure so that fixing credentials in .env and reloading takes effect
    without a full Flask restart.

    Key differences from the original implementation
    ------------------------------------------------
    • validate=False           – skips the Watson Studio profile check at init
    • scope_validation=False   – skips the set.default_project() profile check
    • TextGenParameters        – typed params instead of metanames dict
    • Retry window             – re-attempts after 5 minutes on failure
    • Full step-by-step logging – every stage is logged at INFO or ERROR
    """
    global _wx_model, _wx_init_failed, _wx_retry_after

    # ── Return cached instance if already initialised ─────────────────────────
    if _wx_model is not None:
        return _wx_model

    # ── Honour retry window (don't hammer IBM on every request after a fail) ──
    if _wx_init_failed and _wx_retry_after and datetime.utcnow() < _wx_retry_after:
        return None

    try:
        from ibm_watsonx_ai import APIClient
        from ibm_watsonx_ai.credentials import Credentials
        from ibm_watsonx_ai.foundation_models import ModelInference
        from flask import current_app

        # ── Step 1: Read credentials ──────────────────────────────────────────
        api_key    = current_app.config.get("WATSONX_API_KEY", "").strip()
        project_id = current_app.config.get("WATSONX_PROJECT_ID", "").strip()
        url        = current_app.config.get("WATSONX_URL",
                                            "https://au-syd.ml.cloud.ibm.com").strip()
        model_id   = current_app.config.get("WATSONX_MODEL_ID",
                                            "meta-llama/llama-3-3-70b-instruct").strip()

        logger.info("=== IBM watsonx.ai Initialisation ===")
        logger.info("  URL       : %s", url)
        logger.info("  model_id  : %s", model_id)
        logger.info("  api_key   : %s", api_key[:8] + "***" if len(api_key) > 8 else "[EMPTY]")
        logger.info("  project_id: %s", project_id[:8] + "***" if len(project_id) > 8 else "[EMPTY]")

        # ── Step 2: Validate credentials are present ──────────────────────────
        if not api_key or api_key in ("your-ibm-watsonx-api-key",):
            logger.error(
                "WATSONX_API_KEY is not set or still contains the placeholder value. "
                "Open .env and set a real API key from https://cloud.ibm.com/iam/apikeys"
            )
            _wx_init_failed = True
            _wx_retry_after = datetime.utcnow() + timedelta(minutes=5)
            return None

        if not project_id or project_id in ("your-watsonx-project-id",):
            logger.error(
                "WATSONX_PROJECT_ID is not set or still contains the placeholder value. "
                "Open IBM watsonx.ai, create a project, and copy its GUID to .env"
            )
            _wx_init_failed = True
            _wx_retry_after = datetime.utcnow() + timedelta(minutes=5)
            return None

        # ── Step 3: Build Credentials ─────────────────────────────────────────
        logger.info("Step 3: Creating IBM Credentials object…")
        try:
            creds = Credentials(url=url, api_key=api_key)
            logger.info("  Credentials object created OK")
        except Exception as exc:
            logger.error("  Credentials creation failed: %s", exc)
            _wx_init_failed = True
            _wx_retry_after = datetime.utcnow() + timedelta(minutes=5)
            return None

        # ── Step 4: Create APIClient with scope_validation=False ──────────────
        # scope_validation=False skips the Watson Studio user-profile endpoint
        # call that raises CannotSetProjectOrSpace for accounts that have a
        # valid API key but haven't completed Watson Studio registration.
        logger.info("Step 4: Creating APIClient (scope_validation=False)…")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")   # suppress deprecation noise
                client = APIClient(
                    credentials=creds,
                    project_id=project_id,
                    scope_validation=False,        # FIX 2 – skip profile check
                )
            logger.info("  APIClient created OK. default_project_id=%s",
                        client.default_project_id)
        except Exception as exc:
            logger.error(
                "  APIClient creation failed: %s\n"
                "  Check that WATSONX_PROJECT_ID belongs to YOUR IBM Cloud account "
                "and that you have added it as a project member at "
                "https://dataplatform.cloud.ibm.com/",
                exc,
            )
            _wx_init_failed = True
            _wx_retry_after = datetime.utcnow() + timedelta(minutes=5)
            return None

        # ── Step 5: Create ModelInference with validate=False ─────────────────
        # validate=False skips the get_model_specs() network call at init time.
        # Auth errors will now surface at generate_text() time as ApiRequestFailure
        # with a clear 401/403 HTTP status code and body.
        logger.info("Step 5: Creating ModelInference (validate=False, model=%s)…", model_id)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                _wx_model = ModelInference(
                    model_id=model_id,
                    api_client=client,
                    validate=False,               # FIX 1 – defer auth to call time
                )
            logger.info("  ModelInference created OK – IBM Granite is ready.")
            _wx_init_failed = False
            _wx_retry_after = None
            return _wx_model
        except Exception as exc:
            logger.error("  ModelInference creation failed: %s", exc)
            _wx_model = None
            _wx_init_failed = True
            _wx_retry_after = datetime.utcnow() + timedelta(minutes=5)
            return None

    except ImportError:
        logger.error(
            "ibm-watsonx-ai package is not installed. "
            "Run: pip install ibm-watsonx-ai>=1.0.0"
        )
        _wx_init_failed = True
        _wx_retry_after = datetime.utcnow() + timedelta(minutes=5)
        return None

    except Exception as exc:
        logger.error("Unexpected error initialising watsonx.ai: %s", exc)
        _wx_init_failed = True
        _wx_retry_after = datetime.utcnow() + timedelta(minutes=5)
        return None


def _call_granite(prompt: str, max_tokens: int = 800, temperature: float = 0.7) -> str:
    """
    Send a prompt to the IBM watsonx.ai model and return the generated text.

    Uses the modern Chat Completions API (model.chat()) instead of the
    deprecated /ml/v1/text/generation REST endpoint.  This eliminates the
    SDK 1.6.0 deprecation warnings:
      - 'parameters.decoding_method is ignored and set automatically'
      - '/ml/v1/text/generation API is deprecated, use /ml/v1/text/chat'

    Falls back to the legacy generate_text() if chat() is not available.
    Returns an empty string on any failure so callers fall back gracefully.
    All errors are logged with full detail.
    """
    model = _get_watsonx_model()
    if model is None:
        logger.warning(
            "_call_granite: model is None (credentials invalid or not set). "
            "Falling back to rule-based response."
        )
        return ""

    # Log the first 200 chars of the prompt so we can verify it's sent
    logger.info("Sending prompt to IBM model (%d chars, max_tokens=%d)…",
                len(prompt), max_tokens)
    logger.debug("Prompt preview: %s", prompt[:200].replace("\n", " "))

    try:
        # ── Primary: Chat Completions API (modern, no deprecation warnings) ──
        # model.chat() maps to /ml/v1/text/chat which is the current IBM endpoint.
        # The 'messages' format is the standard OpenAI-compatible messages list.
        chat_params = {
            "max_tokens":  max_tokens,
            "temperature": temperature,
        }
        messages = [{"role": "user", "content": prompt}]

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")   # suppress any residual SDK warnings
            response_obj = model.chat(messages=messages, params=chat_params)

        # Extract text from the chat response structure
        if isinstance(response_obj, dict):
            choices = response_obj.get("choices", [])
            text = choices[0].get("message", {}).get("content", "") if choices else ""
        else:
            # Some SDK versions return an object; convert to str as a safe fallback
            text = str(response_obj)

        if text and text.strip():
            logger.info("IBM model responded (%d chars).", len(text))
            logger.debug("Response preview: %s", text[:200].replace("\n", " "))
            return text.strip()
        else:
            logger.warning("IBM model returned an empty response via chat().")
            return ""

    except AttributeError:
        # chat() not available in this SDK version — fall back to generate_text()
        logger.info("chat() not available, falling back to generate_text().")
        return _call_granite_legacy(prompt, max_tokens, temperature, model)

    except Exception as exc:
        exc_str = str(exc)
        if "401" in exc_str or "Unauthorized" in exc_str or "user_authorization_failed" in exc_str:
            logger.error(
                "IBM AUTH ERROR (401/403): %s\n"
                "  1. WATSONX_API_KEY invalid or expired → https://cloud.ibm.com/iam/apikeys\n"
                "  2. WATSONX_PROJECT_ID from a different account → "
                "https://dataplatform.cloud.ibm.com/\n"
                "  3. Account frozen → upgrade at https://cloud.ibm.com/",
                exc_str[:400],
            )
            _reset_model_cache()
        elif "model_not_supported" in exc_str or "not supported" in exc_str.lower() or "was not found" in exc_str.lower():
            logger.error(
                "IBM MODEL ERROR: model_id '%s' is not available in your region.\n"
                "  au-syd confirmed working model: meta-llama/llama-3-3-70b-instruct\n"
                "  Update WATSONX_MODEL_ID in .env and restart Flask.\n"
                "  Run `flask diagnose-ai` to discover available models.",
                model.model_id if hasattr(model, "model_id") else "unknown",
            )
            _reset_model_cache()
        else:
            logger.error("IBM model chat() error: %s", exc_str[:400])
        return ""


def _call_granite_legacy(
    prompt: str, max_tokens: int, temperature: float, model
) -> str:
    """
    Legacy generate_text() fallback for SDK versions that do not have chat().
    Kept as a safety net; primary path is _call_granite() via chat().
    """
    try:
        from ibm_watsonx_ai.foundation_models.schema import TextGenParameters
        params = TextGenParameters(
            max_new_tokens=max_tokens,
            min_new_tokens=1,
            temperature=temperature,
            top_k=50,
            top_p=0.9,
            repetition_penalty=1.1,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            response = model.generate_text(prompt=prompt, params=params)
        if response and response.strip():
            logger.info("Legacy generate_text responded (%d chars).", len(response))
            return response.strip()
        return ""
    except Exception as exc:
        logger.error("Legacy generate_text error: %s", str(exc)[:300])
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# 2.  AGENT_INSTRUCTIONS Builder
# ─────────────────────────────────────────────────────────────────────────────

def get_agent_instructions() -> str:
    """
    Return the global AGENT_INSTRUCTIONS string sourced from .env config.
    These are prepended to every AI prompt to enforce academic policy,
    response style, safety rules and language.
    """
    try:
        from flask import current_app
        lang    = current_app.config.get("AI_RESPONSE_LANGUAGE", "English")
        style   = current_app.config.get("AI_RESPONSE_STYLE", "detailed")
        context = current_app.config.get("AI_EDUCATION_CONTEXT", "undergraduate")
        safety  = current_app.config.get("AI_SAFETY_LEVEL", "strict")
        custom  = current_app.config.get("AI_CUSTOM_POLICY", "").strip()
        policy  = f"\nInstitutional Policy: {custom}" if custom else ""
        return (
            f"You are EduGuard AI, an intelligent academic advisor for {context} students. "
            f"Always respond in {lang} using a {style} style. "
            f"Safety level: {safety} — keep all responses educational, safe, and professional. "
            f"Never discuss harmful, political, or non-academic topics. "
            f"Focus exclusively on academic performance, study strategies, and student well-being.{policy}"
        )
    except RuntimeError:
        # Outside app context (e.g. tests)
        return (
            "You are EduGuard AI, an intelligent academic advisor. "
            "Keep all responses educational, safe, and professional."
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3.  Academic Health Score (Rule-Based, ML-Ready)
# ─────────────────────────────────────────────────────────────────────────────
#
# Weights are defined as constants here — change them once, affects all logic.
# To plug in an ML model, replace `calculate_health_score` with a call to
# joblib.load('model.pkl').predict([features]) and return the same dict shape.

HEALTH_SCORE_WEIGHTS = {
    "attendance":         0.30,   # 30 %
    "assessment_score":   0.35,   # 35 %
    "faculty_feedback":   0.20,   # 20 %
    "assignment_score":   0.10,   # 10 %
    "previous_gpa":       0.05,   # 5  %
}

RISK_THRESHOLDS = {
    "low":    70,   # score >= 70  →  Low Risk  (green)
    "medium": 45,   # score >= 45  →  Medium Risk (yellow)
    # score < 45   →  High Risk   (red)
}


def calculate_health_score(
    attendance_pct: float,
    assessment_avg: float,
    faculty_feedback_avg: float,   # 1–5 scale → normalised to 0–100
    assignment_avg: float,
    previous_gpa: float,           # 0–10 scale → normalised to 0–100
) -> dict:
    """
    Compute the Academic Health Score and risk classification.

    Parameters (all expected as percentages 0–100 unless noted):
        attendance_pct      : attendance percentage (0–100)
        assessment_avg      : average assessment score (0–100)
        faculty_feedback_avg: average faculty rating (0–5), auto-normalised
        assignment_avg      : average assignment score percentage (0–100)
        previous_gpa        : latest GPA (0–10), auto-normalised

    Returns a dict with keys:
        score         : float  0–100
        risk_level    : "low" | "medium" | "high"
        risk_pct      : float  0–100  (inverse of health)
        color         : "success" | "warning" | "danger"
        breakdown     : dict of individual weighted contributions
    """
    # Normalise inputs that aren't already on 0–100 scale
    feedback_norm = min((faculty_feedback_avg / 5.0) * 100, 100)
    gpa_norm      = min((previous_gpa / 10.0) * 100, 100)

    # Clamp all values
    att   = max(0.0, min(100.0, attendance_pct))
    ass   = max(0.0, min(100.0, assessment_avg))
    fb    = max(0.0, min(100.0, feedback_norm))
    asgn  = max(0.0, min(100.0, assignment_avg))
    gpa   = max(0.0, min(100.0, gpa_norm))

    w = HEALTH_SCORE_WEIGHTS
    score = (
        att  * w["attendance"] +
        ass  * w["assessment_score"] +
        fb   * w["faculty_feedback"] +
        asgn * w["assignment_score"] +
        gpa  * w["previous_gpa"]
    )
    score = round(score, 2)

    if score >= RISK_THRESHOLDS["low"]:
        risk_level = "low"
        color      = "success"
    elif score >= RISK_THRESHOLDS["medium"]:
        risk_level = "medium"
        color      = "warning"
    else:
        risk_level = "high"
        color      = "danger"

    return {
        "score":      score,
        "risk_level": risk_level,
        "risk_pct":   round(100 - score, 2),
        "color":      color,
        "breakdown": {
            "attendance":       {"value": att,  "weight": w["attendance"],       "contribution": round(att  * w["attendance"],       2)},
            "assessment_score": {"value": ass,  "weight": w["assessment_score"], "contribution": round(ass  * w["assessment_score"], 2)},
            "faculty_feedback": {"value": fb,   "weight": w["faculty_feedback"], "contribution": round(fb   * w["faculty_feedback"], 2)},
            "assignment_score": {"value": asgn, "weight": w["assignment_score"], "contribution": round(asgn * w["assignment_score"], 2)},
            "previous_gpa":     {"value": gpa,  "weight": w["previous_gpa"],     "contribution": round(gpa  * w["previous_gpa"],     2)},
        },
    }


def get_student_health_score(student) -> dict:
    """
    Convenience wrapper: compute the health score for a Student ORM object.
    Pulls all data from the student's related records.
    """
    from models import AttendanceStatusEnum, AssessmentAttempt, Assignment, FacultyFeedback
    from sqlalchemy import func
    from database import db

    # Attendance
    total_att = student.attendance_records.count()
    present   = student.attendance_records.filter_by(status=AttendanceStatusEnum.PRESENT).count()
    att_pct   = round((present / total_att * 100), 2) if total_att else 0.0

    # Assessment average
    result = db.session.query(func.avg(AssessmentAttempt.percentage)).filter_by(
        student_id=student.id, is_completed=True
    ).scalar()
    assessment_avg = round(result or 0, 2)

    # Faculty feedback average (overall_rating is 1–5)
    fb_result = db.session.query(func.avg(FacultyFeedback.overall_rating)).filter_by(
        student_id=student.id
    ).scalar()
    feedback_avg = round(fb_result or 0, 2)

    # Assignment average
    assignments = student.assignments.filter(Assignment.obtained_marks.isnot(None)).all()
    if assignments:
        assignment_avg = round(
            sum(a.obtained_marks / a.max_marks * 100 for a in assignments if a.max_marks) / len(assignments), 2
        )
    else:
        assignment_avg = 0.0

    # Previous GPA (0–10 scale)
    prev_gpa = student.latest_gpa or 0.0

    return calculate_health_score(att_pct, assessment_avg, feedback_avg, assignment_avg, prev_gpa)


# ─────────────────────────────────────────────────────────────────────────────
# 4.  Prompt Builders
# ─────────────────────────────────────────────────────────────────────────────

def _build_assessment_analysis_prompt(attempt, answers, student) -> str:
    """Build the Granite prompt for post-assessment AI analysis."""
    agent = get_agent_instructions()

    # Collect per-question detail (topic + correctness)
    wrong_topics = []
    right_topics = []
    for ans in answers:
        unit_name  = ans.question.unit.name if ans.question.unit else "General"
        difficulty = ans.question.difficulty.capitalize()
        if ans.is_correct:
            right_topics.append(f"{unit_name} ({difficulty})")
        else:
            wrong_topics.append(f"{unit_name} ({difficulty})")

    wrong_summary = ", ".join(set(wrong_topics)) if wrong_topics else "None"
    right_summary = ", ".join(set(right_topics)) if right_topics else "None"

    prompt = f"""{agent}

===  ASSESSMENT ANALYSIS REQUEST  ===

Student: {student.full_name} | ID: {student.student_id}
Subject: {attempt.assessment.subject.name}
Assessment: {attempt.assessment.title}
Date: {attempt.submitted_at.strftime('%d %b %Y') if attempt.submitted_at else 'N/A'}

Performance Data:
- Score: {attempt.score} / {attempt.assessment.max_marks}
- Percentage: {attempt.percentage}%
- Correct: {attempt.correct_answers} / {attempt.total_questions} questions
- Time Taken: {(attempt.time_taken_seconds // 60) if attempt.time_taken_seconds else 'N/A'} minutes
- Topics with Correct Answers: {right_summary}
- Topics with Wrong Answers: {wrong_summary}

Based on this real assessment data, generate a structured educational analysis with these exact sections:

1. OVERALL ASSESSMENT SUMMARY
2. ACADEMIC HEALTH SCORE ANALYSIS
3. CONCEPT UNDERSTANDING LEVEL
4. CONFIDENCE LEVEL
5. WEAK TOPICS
6. STRONG TOPICS
7. LEARNING PATTERN
8. MISTAKES ANALYSIS
9. PERSONALIZED STUDY RECOMMENDATIONS
10. SUBJECT-WISE IMPROVEMENT SUGGESTIONS
11. TIME MANAGEMENT ADVICE
12. EXAM PREPARATION TIPS
13. MOTIVATION MESSAGE

Use the actual assessment data. Be specific, practical, and encouraging.

ANALYSIS:
"""
    return prompt


def _build_risk_analysis_prompt(student, health_data: dict) -> str:
    """Build the Granite prompt for AI Risk Analysis report."""
    agent = get_agent_instructions()

    from models import AttendanceStatusEnum, AssessmentAttempt, FacultyFeedback
    from sqlalchemy import func
    from database import db

    # Gather summaries
    total_att = student.attendance_records.count()
    present   = student.attendance_records.filter_by(status=AttendanceStatusEnum.PRESENT).count()
    att_pct   = round((present / total_att * 100), 2) if total_att else 0.0

    total_attempts = student.assessment_attempts.filter_by(is_completed=True).count()
    avg_pct = db.session.query(func.avg(AssessmentAttempt.percentage)).filter_by(
        student_id=student.id, is_completed=True
    ).scalar() or 0

    fb_result = db.session.query(func.avg(FacultyFeedback.overall_rating)).filter_by(
        student_id=student.id
    ).scalar() or 0
    latest_fb  = student.feedbacks.order_by(FacultyFeedback.created_at.desc()).first()
    fb_comment = latest_fb.comments if latest_fb and latest_fb.comments else "No comments on record."

    prompt = f"""{agent}

===  ACADEMIC RISK ANALYSIS REQUEST  ===

Student: {student.full_name} | ID: {student.student_id}
Department: {student.department.name if student.department else 'N/A'}
Semester: {student.current_semester}

Academic Data:
- Attendance: {att_pct}% ({present}/{total_att} classes)
- Assessment Average: {round(avg_pct, 1)}% over {total_attempts} attempts
- Faculty Feedback Rating: {round(fb_result, 2)}/5
- Latest Faculty Comment: "{fb_comment}"
- Previous GPA: {student.latest_gpa}
- Academic Health Score: {health_data['score']}/100
- Current Risk Level: {health_data['risk_level'].upper()}

Score Breakdown:
- Attendance Contribution: {health_data['breakdown']['attendance']['contribution']}
- Assessment Contribution: {health_data['breakdown']['assessment_score']['contribution']}
- Feedback Contribution: {health_data['breakdown']['faculty_feedback']['contribution']}
- Assignment Contribution: {health_data['breakdown']['assignment_score']['contribution']}
- GPA Contribution: {health_data['breakdown']['previous_gpa']['contribution']}

Generate a comprehensive risk analysis with these exact sections:

1. RISK LEVEL (Low / Medium / High with reasoning)
2. DROPOUT RISK (percentage estimate and key factors)
3. ACADEMIC WEAKNESSES (specific areas needing improvement)
4. LEARNING BEHAVIOR SUMMARY (patterns observed from data)
5. IMPROVEMENT PRIORITY (top 3 actionable priorities ranked)
6. SUGGESTED WEEKLY STUDY PLAN (Day-wise schedule for 7 days)

Use the actual data. Be empathetic, constructive, and specific.

RISK ANALYSIS:
"""
    return prompt


def _build_chatbot_prompt(user_message: str, student=None) -> str:
    """Build the Granite prompt for the AI Academic Advisor chatbot."""
    agent = get_agent_instructions()
    student_ctx = ""
    if student:
        student_ctx = (
            f"\nStudent context: {student.full_name}, Semester {student.current_semester}, "
            f"Department: {student.department.name if student.department else 'N/A'}"
        )

    prompt = f"""{agent}{student_ctx}

You are an AI Academic Advisor chatbot. Answer only educational questions about:
- Subject doubts and explanations
- Study planning and strategies
- Topic explanations
- Exam preparation tips
- Time management for students
- Motivation and learning strategies
- Personalized academic guidance

If the user asks anything outside academics, politely redirect to academic topics.

Student Question: {user_message}

AI Advisor Response:
"""
    return prompt


# ─────────────────────────────────────────────────────────────────────────────
# 5.  Public API Functions (called by blueprints)
# ─────────────────────────────────────────────────────────────────────────────

def analyze_assessment(attempt_id: int) -> Optional[dict]:
    """
    Generate and store AI analysis for a completed assessment attempt.
    Returns a dict with 'analysis_text' and 'sections' keys, or None on error.
    """
    try:
        from models import AssessmentAttempt, AIAnalysisResult
        from database import db

        attempt = AssessmentAttempt.query.get(attempt_id)
        if not attempt or not attempt.is_completed:
            return None

        # Check cache: return existing analysis if already generated
        existing = AIAnalysisResult.query.filter_by(
            attempt_id=attempt_id,
            analysis_type="assessment"
        ).first()
        if existing:
            return {"analysis_text": existing.analysis_text, "sections": existing.get_sections()}

        answers = attempt.answers.all()
        student = attempt.student

        from flask import current_app
        max_tokens  = current_app.config.get("AI_MAX_TOKENS", 800)
        temperature = current_app.config.get("AI_TEMPERATURE", 0.7)

        prompt = _build_assessment_analysis_prompt(attempt, answers, student)
        raw    = _call_granite(prompt, max_tokens=max_tokens, temperature=temperature)

        if not raw:
            logger.info("Using rule-based fallback for assessment analysis (attempt %d)", attempt_id)
            raw = _generate_fallback_assessment_analysis(attempt, answers)

        sections = _parse_numbered_sections(raw)

        # Persist to database
        record = AIAnalysisResult(
            student_id=student.id,
            attempt_id=attempt_id,
            analysis_type="assessment",
            analysis_text=raw,
            sections_json=json.dumps(sections),
            generated_at=datetime.utcnow()
        )
        db.session.add(record)

        # Update student risk score
        health = get_student_health_score(student)
        prev_risk = student.risk_level
        student.academic_health_score = health["score"]
        student.risk_level            = health["risk_level"]
        student.risk_updated_at       = datetime.utcnow()
        db.session.commit()

        # Send email alert if risk level is medium or high
        try:
            from email_service import send_risk_alert
            if health["risk_level"] in ("medium", "high"):
                send_risk_alert(student)
        except Exception as mail_exc:
            logger.warning("Email alert failed (non-fatal): %s", mail_exc)

        return {"analysis_text": raw, "sections": sections}

    except Exception as exc:
        logger.error("analyze_assessment error: %s", exc)
        return None


def generate_risk_report(student_id: int, force_refresh: bool = False) -> Optional[dict]:
    """
    Generate and store a full AI Risk Report for a student.
    Returns a dict with 'analysis_text', 'sections', and 'health_data' keys.
    """
    try:
        from models import Student, AIAnalysisResult
        from database import db
        from flask import current_app

        student = Student.query.get(student_id)
        if not student:
            return None

        health = get_student_health_score(student)

        # Update student's stored health score
        student.academic_health_score = health["score"]
        student.risk_level            = health["risk_level"]
        student.risk_updated_at       = datetime.utcnow()
        db.session.commit()

        # Check cache (24-hour freshness)
        if not force_refresh:
            existing = AIAnalysisResult.query.filter_by(
                student_id=student_id,
                analysis_type="risk_report"
            ).order_by(AIAnalysisResult.generated_at.desc()).first()
            if existing:
                age_hours = (datetime.utcnow() - existing.generated_at).total_seconds() / 3600
                if age_hours < 24:
                    return {
                        "analysis_text": existing.analysis_text,
                        "sections":      existing.get_sections(),
                        "health_data":   health,
                    }

        max_tokens  = current_app.config.get("AI_MAX_TOKENS", 800)
        temperature = current_app.config.get("AI_TEMPERATURE", 0.7)

        prompt = _build_risk_analysis_prompt(student, health)
        raw    = _call_granite(prompt, max_tokens=max_tokens, temperature=temperature)

        if not raw:
            logger.info("Using rule-based fallback for risk report (student %d)", student_id)
            raw = _generate_fallback_risk_analysis(student, health)

        sections = _parse_numbered_sections(raw)

        record = AIAnalysisResult(
            student_id=student.id,
            analysis_type="risk_report",
            analysis_text=raw,
            sections_json=json.dumps(sections),
            generated_at=datetime.utcnow()
        )
        db.session.add(record)
        db.session.commit()

        return {"analysis_text": raw, "sections": sections, "health_data": health}

    except Exception as exc:
        logger.error("generate_risk_report error: %s", exc)
        return None


def chat_with_advisor(user_message: str, student=None) -> str:
    """
    Send a message to the AI Academic Advisor chatbot.
    Returns the AI response text (or a safe rule-based fallback).
    """
    if not user_message or not user_message.strip():
        return "Please ask a question so I can help you!"

    try:
        from flask import current_app
        max_tokens  = min(current_app.config.get("AI_MAX_TOKENS", 800), 800)
        temperature = current_app.config.get("AI_TEMPERATURE", 0.7)
    except RuntimeError:
        max_tokens, temperature = 600, 0.7

    logger.info("Chatbot request: '%s'", user_message[:80])
    prompt   = _build_chatbot_prompt(user_message.strip(), student)
    response = _call_granite(prompt, max_tokens=max_tokens, temperature=temperature)

    if not response:
        logger.info("Chatbot: Granite unavailable, returning rule-based fallback.")
        return _generate_fallback_chat_response(user_message)
    return response


# ─────────────────────────────────────────────────────────────────────────────
# 6.  Text Parsers & Fallback Generators
# ─────────────────────────────────────────────────────────────────────────────

def _parse_numbered_sections(text: str) -> dict:
    """
    Parse numbered sections from Granite output into a dict.
    E.g. '1. OVERALL ASSESSMENT SUMMARY\n...\n2. ACADEMIC HEALTH SCORE' → dict
    """
    import re
    sections = {}
    # Split on patterns like "1. SECTION NAME" or "1. Section Name"
    parts = re.split(r'\n(?=\d+\.\s+[A-Z])', text.strip())
    for part in parts:
        match = re.match(r'^(\d+)\.\s+(.+?)(?:\n|$)(.*)', part.strip(), re.DOTALL)
        if match:
            heading = match.group(2).strip().upper().replace(" ", "_")
            body    = match.group(3).strip()
            sections[heading] = body
    return sections


def _generate_fallback_assessment_analysis(attempt, answers) -> str:
    """
    Rule-based fallback when IBM Granite is unavailable.
    Generates meaningful text from the actual assessment data.
    """
    pct     = attempt.percentage
    correct = attempt.correct_answers
    total   = attempt.total_questions
    wrong   = total - correct
    subject = attempt.assessment.subject.name

    if pct >= 80:
        level = "Excellent"; recommendation = "Keep up the outstanding work!"
        confidence = "High"; health = "Strong academic health."
    elif pct >= 60:
        level = "Good"; recommendation = "Focus on weak areas for further improvement."
        confidence = "Moderate"; health = "Satisfactory academic health."
    elif pct >= 40:
        level = "Average"; recommendation = "Increase study hours and practice more questions."
        confidence = "Low-Moderate"; health = "Academic health needs attention."
    else:
        level = "Needs Improvement"; recommendation = "Seek faculty guidance and revise fundamentals."
        confidence = "Low"; health = "Academic health is at risk — immediate action required."

    wrong_units = list(set(
        a.question.unit.name for a in answers if not a.is_correct and a.question.unit
    ))
    right_units = list(set(
        a.question.unit.name for a in answers if a.is_correct and a.question.unit
    ))

    return f"""1. OVERALL ASSESSMENT SUMMARY
You scored {pct}% ({correct}/{total} correct) in {subject}. Performance level: {level}.

2. ACADEMIC HEALTH SCORE ANALYSIS
{health} Score of {pct}% reflects your current mastery of this subject's topics.

3. CONCEPT UNDERSTANDING LEVEL
{level} understanding demonstrated. {'Strong grasp of most concepts tested.' if pct >= 60 else 'Several foundational concepts need revision.'}

4. CONFIDENCE LEVEL
{confidence} confidence based on your response pattern. {'Your consistent correct answers show solid preparation.' if pct >= 60 else 'Building confidence through regular practice will help.'}

5. WEAK TOPICS
{', '.join(wrong_units) if wrong_units else 'None identified — well done!'} — {wrong} question(s) answered incorrectly.

6. STRONG TOPICS
{', '.join(right_units) if right_units else 'Build on current knowledge'} — {correct} question(s) answered correctly.

7. LEARNING PATTERN
{'Consistent performance suggesting systematic study habits.' if pct >= 60 else 'Inconsistent performance suggests gaps in preparation. Consider structured revision.'}

8. MISTAKES ANALYSIS
{wrong} out of {total} questions were incorrect. {'Minor errors — review explanations for wrong answers.' if wrong <= 3 else 'Multiple conceptual gaps detected. Revisit incorrect topics systematically.'}

9. PERSONALIZED STUDY RECOMMENDATIONS
- Review all incorrect answers and their explanations immediately.
- Spend 30 minutes daily on {wrong_units[0] if wrong_units else subject} concepts.
- Practice at least 10 additional questions per weak topic.
- {recommendation}

10. SUBJECT-WISE IMPROVEMENT SUGGESTIONS
For {subject}: {'Maintain your strong performance by exploring advanced topics.' if pct >= 75 else 'Start with the fundamentals of weak units before advancing to complex problems.'}

11. TIME MANAGEMENT ADVICE
{'You managed the assessment time effectively.' if attempt.time_taken_seconds and attempt.time_taken_seconds < attempt.assessment.duration_minutes * 60 * 0.8 else 'Practice timed mock tests to improve your speed and accuracy.'}

12. EXAM PREPARATION TIPS
- Create a topic-wise checklist for {subject}.
- Solve previous year questions for each unit.
- Discuss doubts with your faculty within 24 hours of each assessment.

13. MOTIVATION MESSAGE
{'Excellent work! Your dedication to learning is paying off. Keep challenging yourself with harder problems.' if pct >= 75 else 'Every expert was once a beginner. Use this assessment as a learning opportunity — you have the potential to excel!'}
"""


def _generate_fallback_risk_analysis(student, health: dict) -> str:
    """Rule-based fallback risk analysis when IBM Granite is unavailable."""
    score = health["score"]
    risk  = health["risk_level"]
    bd    = health["breakdown"]

    risk_pct_estimate = max(5, round(100 - score, 0))
    weakest = min(bd, key=lambda k: bd[k]["contribution"])

    study_plan_note = (
        "intensive daily study sessions" if risk == "high"
        else "consistent daily study sessions" if risk == "medium"
        else "regular study sessions"
    )

    return f"""1. RISK LEVEL
{risk.upper()} RISK — Academic Health Score: {score}/100.
{'Immediate academic intervention recommended.' if risk == 'high' else 'Moderate improvement needed across key areas.' if risk == 'medium' else 'Student is on track. Maintain current momentum.'}

2. DROPOUT RISK
Estimated dropout risk: {risk_pct_estimate}%. {'Key contributing factors: low attendance and assessment performance.' if risk == 'high' else 'Key factor: ' + weakest + ' needs improvement.'}

3. ACADEMIC WEAKNESSES
- Attendance contribution is {bd['attendance']['contribution']}/30 points.
- Assessment score contribution is {bd['assessment_score']['contribution']}/35 points.
- Faculty feedback contribution is {bd['faculty_feedback']['contribution']}/20 points.
- Assignment performance contribution is {bd['assignment_score']['contribution']}/10 points.
- GPA contribution is {bd['previous_gpa']['contribution']}/5 points.

4. LEARNING BEHAVIOR SUMMARY
Student demonstrates {'strong engagement and consistent academic effort' if score >= 70 else 'moderate engagement with areas of inconsistency' if score >= 45 else 'low engagement requiring immediate faculty support'}. Current academic health score of {score} indicates {'healthy progress' if score >= 70 else 'need for structured support' if score >= 45 else 'critical intervention need'}.

5. IMPROVEMENT PRIORITY
1. {'Increase attendance to at least 85%' if bd['attendance']['value'] < 75 else 'Maintain strong attendance'}
2. {'Improve assessment scores through daily practice tests' if bd['assessment_score']['value'] < 60 else 'Sustain assessment performance'}
3. {'Seek faculty feedback and act on suggestions' if bd['faculty_feedback']['value'] < 60 else 'Maintain positive faculty relationship'}

6. SUGGESTED WEEKLY STUDY PLAN
Monday:    Subject review + 1 hour practice questions
Tuesday:   Weak topic deep-dive + concept mapping
Wednesday: Assignment completion + faculty consultation
Thursday:  Mock test under timed conditions
Friday:    Error analysis + revisit incorrect answers
Saturday:  {study_plan_note} for upcoming assessments
Sunday:    Rest, light review, and plan next week
"""


def _generate_fallback_chat_response(user_message: str) -> str:
    """
    Intelligent rule-based chatbot fallback using keyword matching.
    Returns a helpful academic response even without IBM Granite.
    """
    msg = user_message.lower()

    if any(w in msg for w in ["study", "how to study", "study tips", "study plan", "study strategy"]):
        return (
            "Here are effective study strategies:\n\n"
            "1. **Spaced Repetition** – Review material at increasing intervals (1 day, 3 days, 1 week)\n"
            "2. **Active Recall** – Test yourself instead of re-reading notes\n"
            "3. **Pomodoro Technique** – Study for 25 minutes, rest 5 minutes\n"
            "4. **Concept Mapping** – Draw connections between topics\n"
            "5. **Teach Back** – Explain concepts in your own words\n\n"
            "Would you like a personalised study plan for a specific subject?"
        )
    elif any(w in msg for w in ["exam", "test", "preparation", "prepare", "revision"]):
        return (
            "Exam preparation tips:\n\n"
            "• Start revision at least 2 weeks before the exam\n"
            "• Solve previous year question papers under timed conditions\n"
            "• Focus on high-weightage topics first\n"
            "• Avoid cramming — understand concepts, don't memorise blindly\n"
            "• Get 7–8 hours of sleep the night before the exam\n"
            "• Review your mistakes from past assessments on EduGuard AI\n\n"
            "Which subject are you preparing for?"
        )
    elif any(w in msg for w in ["time", "manage", "schedule", "plan", "routine", "procrastinat"]):
        return (
            "Time management for students:\n\n"
            "🕗 **Morning (6–8 AM)** – Most complex/difficult subjects\n"
            "📚 **Morning Classes** – Active participation\n"
            "🌙 **Evening (6–8 PM)** – Review and practice problems\n"
            "📝 **Night** – Light reading, revision, and next day planning\n\n"
            "Use the Eisenhower Matrix:\n"
            "• Urgent + Important → Do immediately\n"
            "• Not Urgent + Important → Schedule it\n"
            "• Urgent + Not Important → Delegate\n"
            "• Not Urgent + Not Important → Eliminate\n\n"
            "What specific time management challenge are you facing?"
        )
    elif any(w in msg for w in ["motivat", "stress", "depress", "anxious", "tired", "burn", "give up"]):
        return (
            "I understand academic pressure can feel overwhelming. Here are evidence-based strategies:\n\n"
            "✨ **Mindset** – Focus on progress, not perfection. Every small improvement counts.\n"
            "🎯 **Small Goals** – Break big tasks into 15-minute action items\n"
            "🏃 **Exercise** – Even a 20-minute walk improves focus and mood\n"
            "💤 **Sleep** – Prioritise 7–8 hours; sleep consolidates memory\n"
            "🤝 **Support** – Talk to your faculty or a mentor\n\n"
            "Remember: checking your Academic Health Score on EduGuard AI regularly helps you "
            "stay on track before small issues become big problems."
        )
    elif any(w in msg for w in ["attendance", "absent", "miss class"]):
        return (
            "Regarding attendance:\n\n"
            "• Maintaining ≥75% attendance is required at most institutions\n"
            "• Missing classes creates knowledge gaps that compound over time\n"
            "• If you missed a class: review notes from a classmate, watch related videos, "
            "and use your textbook to cover the topic\n"
            "• Check your attendance percentage on the EduGuard AI Student Dashboard\n\n"
            "Is there a specific reason you're missing classes? I can help with strategies."
        )
    elif any(w in msg for w in ["gpa", "grade", "cgpa", "marks", "score", "percentage", "fail"]):
        return (
            "Improving your academic scores:\n\n"
            "📊 **Check your AI Academic Report** on EduGuard AI to identify weak topics\n"
            "📝 **Assignments** – Submit on time; quality > quantity\n"
            "🎯 **Focus on weak subjects first** – Use 60% study time on your weakest areas\n"
            "❓ **Ask questions** – Visit faculty during office hours\n"
            "📚 **Practice** – Solve at least 10 questions daily per subject\n\n"
            "Your Academic Health Score on EduGuard AI considers GPA, attendance, feedback, "
            "and assessment results together. View your full AI Report for personalised guidance."
        )
    else:
        # Generic academic guidance
        return (
            "I'm your AI Academic Advisor, here to help with:\n\n"
            "📚 **Study strategies** – Ask 'how to study effectively'\n"
            "📝 **Exam preparation** – Ask 'tips for exam preparation'\n"
            "⏰ **Time management** – Ask 'how to manage my study time'\n"
            "💡 **Subject doubts** – Ask about any topic you're struggling with\n"
            "💪 **Motivation** – Ask 'I'm feeling stressed about exams'\n\n"
            "What would you like help with today?"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 7.  Diagnostic Function (used by flask diagnose-ai CLI command)
# ─────────────────────────────────────────────────────────────────────────────

def run_diagnostics() -> dict:
    """
    Run a full IBM watsonx.ai connectivity diagnostic and return a structured
    result dict.  Called by the `flask diagnose-ai` CLI command.
    """
    import os, requests
    from dotenv import load_dotenv

    load_dotenv(override=True)

    result = {
        "env_loaded":         False,
        "api_key_set":        False,
        "project_id_set":     False,
        "iam_token":          False,
        "account_frozen":     False,
        "account_id":         None,
        "direct_rest_status": None,
        "direct_rest_text":   None,
        "sdk_init":           False,
        "sdk_generate":       False,
        "errors":             [],
    }

    # ── 1. Check env vars ─────────────────────────────────────────────────────
    api_key    = os.environ.get("WATSONX_API_KEY", "").strip()
    project_id = os.environ.get("WATSONX_PROJECT_ID", "").strip()
    url        = os.environ.get("WATSONX_URL", "https://au-syd.ml.cloud.ibm.com").strip()
    model_id   = os.environ.get("WATSONX_MODEL_ID", "meta-llama/llama-3-3-70b-instruct").strip()

    result["env_loaded"]   = True
    result["api_key_set"]  = bool(api_key) and api_key not in ("your-ibm-watsonx-api-key",)
    result["project_id_set"] = bool(project_id) and project_id not in ("your-watsonx-project-id",)

    if not result["api_key_set"]:
        result["errors"].append("WATSONX_API_KEY not set or is still a placeholder")
        return result
    if not result["project_id_set"]:
        result["errors"].append("WATSONX_PROJECT_ID not set or is still a placeholder")
        return result

    # ── 2. Test IBM Cloud IAM token ───────────────────────────────────────────
    try:
        iam_resp = requests.post(
            "https://iam.cloud.ibm.com/identity/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": api_key},
            timeout=15,
        )
        if iam_resp.status_code == 200:
            result["iam_token"] = True
            token = iam_resp.json().get("access_token", "")

            # Decode JWT to check account state
            import base64, json as _json
            parts = token.split(".")
            if len(parts) >= 2:
                p = parts[1] + "=" * (4 - len(parts[1]) % 4)
                payload = _json.loads(base64.b64decode(p))
                acct = payload.get("account", {})
                result["account_id"]     = acct.get("bss")
                result["account_frozen"] = acct.get("frozen", False)
        else:
            result["errors"].append(
                f"IAM token failed: HTTP {iam_resp.status_code} – {iam_resp.text[:200]}"
            )
            return result
    except Exception as e:
        result["errors"].append(f"IAM request error: {e}")
        return result

    # ── 3. Discover available text-generation models in this region ───────────
    result["available_models"]     = []
    result["recommended_model"]    = None
    try:
        catalogue_url = f"{url}/ml/v1/foundation_model_specs?version=2023-05-29&limit=200"
        cat_resp = requests.get(
            catalogue_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        if cat_resp.status_code == 200:
            resources = cat_resp.json().get("resources", [])
            text_gen_models = []
            for m in resources:
                mid      = m.get("model_id", "")
                tasks    = [t.get("id", "") for t in m.get("tasks", [])]
                lifecycle = [s.get("id", "") for s in m.get("lifecycle", [])]
                # Include only non-withdrawn models that list text generation tasks
                gen_tasks = {"text_generation", "generation", "question_answering",
                             "summarization", "retrieval_augmented_generation"}
                if gen_tasks.intersection(tasks) and "withdrawn" not in lifecycle:
                    text_gen_models.append(mid)
            result["available_models"] = text_gen_models
            # Best pick: prefer instruct/chat models, then base models
            for mid in text_gen_models:
                if "instruct" in mid.lower() or "chat" in mid.lower():
                    result["recommended_model"] = mid
                    break
            if not result["recommended_model"] and text_gen_models:
                result["recommended_model"] = text_gen_models[0]
        else:
            result["errors"].append(
                f"Model catalogue failed: HTTP {cat_resp.status_code}"
            )
    except Exception as e:
        result["errors"].append(f"Model catalogue error: {e}")

    # ── 4. Direct REST generation test ───────────────────────────────────────
    try:
        gen_url = f"{url}/ml/v1/text/generation?version=2023-05-29"
        h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {
            "model_id": model_id,
            "input": "What is 2+2? Answer in one word:",
            "parameters": {"max_new_tokens": 10, "decoding_method": "greedy", "min_new_tokens": 1},
            "project_id": project_id,
        }
        gen_resp = requests.post(gen_url, headers=h, json=body, timeout=20)
        result["direct_rest_status"] = gen_resp.status_code
        if gen_resp.status_code == 200:
            result["direct_rest_text"] = (
                gen_resp.json().get("results", [{}])[0].get("generated_text", "").strip()
            )
        else:
            err_body = gen_resp.json()
            err_msgs = [e.get("message", "") for e in err_body.get("errors", [])]
            result["errors"].append(
                f"Direct REST failed: HTTP {gen_resp.status_code} – {'; '.join(err_msgs)[:300]}"
            )
    except Exception as e:
        result["errors"].append(f"Direct REST request error: {e}")

    # ── 5. SDK init + generate test ───────────────────────────────────────────
    try:
        from ibm_watsonx_ai import APIClient
        from ibm_watsonx_ai.credentials import Credentials
        from ibm_watsonx_ai.foundation_models import ModelInference
        from ibm_watsonx_ai.foundation_models.schema import TextGenParameters

        creds = Credentials(url=url, api_key=api_key)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            client = APIClient(credentials=creds, project_id=project_id, scope_validation=False)
            model  = ModelInference(model_id=model_id, api_client=client, validate=False)

        result["sdk_init"] = True

        # Use chat() (modern API) — no deprecation warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            chat_resp = model.chat(
                messages=[{"role": "user", "content": "What is 2+2? Answer with just the number:"}],
                params={"max_tokens": 10, "temperature": 0.0},
            )
        if isinstance(chat_resp, dict):
            choices = chat_resp.get("choices", [])
            resp_text = choices[0].get("message", {}).get("content", "").strip() if choices else ""
        else:
            resp_text = str(chat_resp).strip()

        result["sdk_generate"] = bool(resp_text)
        if result["sdk_generate"]:
            result["direct_rest_text"] = resp_text
    except Exception as e:
        result["errors"].append(f"SDK error: {type(e).__name__}: {str(e)[:300]}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 8.  AI Question Generator (called by Faculty Question Bank)
# ─────────────────────────────────────────────────────────────────────────────

def generate_ai_questions(
    subject_name: str,
    unit_name: str,
    difficulty: str,
    question_type: str,
    count: int = 5,
    topic_hint: str = "",
) -> list:
    """
    Use IBM Granite to generate quiz questions for the given subject/unit.

    Parameters:
        subject_name  : e.g. "Data Structures"
        unit_name     : e.g. "Trees"
        difficulty    : "easy" | "medium" | "hard"
        question_type : "mcq" | "true_false" | "fill_blank"
        count         : number of questions to generate (1–10)
        topic_hint    : optional extra context, e.g. "binary search trees"

    Returns a list of dicts with keys:
        question_text, option_a, option_b, option_c, option_d,
        correct_answer, explanation, difficulty, question_type
    Returns empty list on failure so caller falls back gracefully.
    """
    count = max(1, min(count, 10))  # clamp 1–10

    type_instructions = {
        "mcq": (
            "Generate multiple-choice questions. Each question must have exactly 4 options "
            "(A, B, C, D). Correct answer should be one letter: a, b, c, or d."
        ),
        "true_false": (
            "Generate True/False questions. Options must be 'True' and 'False'. "
            "Correct answer must be exactly 'true' or 'false' (lowercase)."
        ),
        "fill_blank": (
            "Generate fill-in-the-blank questions. Use ___ for the blank. "
            "Correct answer is the exact word or phrase that fills the blank."
        ),
    }

    agent = get_agent_instructions()
    topic_str = f" (focus on: {topic_hint})" if topic_hint.strip() else ""
    q_type_instr = type_instructions.get(question_type, type_instructions["mcq"])

    prompt = f"""{agent}

=== QUESTION GENERATION REQUEST ===

Subject     : {subject_name}
Unit        : {unit_name}{topic_str}
Difficulty  : {difficulty.capitalize()}
Type        : {question_type.replace('_', ' ').title()}
Count       : {count}

Instructions:
{q_type_instr}

Generate exactly {count} {difficulty} {question_type.replace('_', ' ')} question(s) for the topic above.

IMPORTANT: Respond ONLY with a JSON array. No markdown, no explanation. Example format:
[
  {{
    "question_text": "What is ...?",
    "option_a": "Answer A",
    "option_b": "Answer B",
    "option_c": "Answer C",
    "option_d": "Answer D",
    "correct_answer": "a",
    "explanation": "Because ..."
  }}
]

For true_false: set option_a="True", option_b="False", option_c="", option_d="".
For fill_blank: set all options to "".

JSON ARRAY:
"""

    try:
        from flask import current_app
        max_tokens  = min(current_app.config.get("AI_MAX_TOKENS", 1500), 2000)
        temperature = 0.6   # slightly lower for structured output
    except RuntimeError:
        max_tokens, temperature = 1200, 0.6

    logger.info("AI Question Generator: subject=%s unit=%s type=%s count=%d",
                subject_name, unit_name, question_type, count)

    raw = _call_granite(prompt, max_tokens=max_tokens, temperature=temperature)

    if not raw:
        logger.info("AI Question Generator: Granite unavailable, returning empty list.")
        return []

    # ── Parse JSON from Granite response ────────────────────────────────────
    import re
    # Extract JSON array from response (Granite sometimes adds preamble)
    json_match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not json_match:
        logger.warning("AI Question Generator: no JSON array found in response.")
        return []

    try:
        questions = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        logger.warning("AI Question Generator: JSON parse failed: %s", e)
        return []

    if not isinstance(questions, list):
        return []

    # ── Validate and normalise each question ────────────────────────────────
    validated = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        q_text = str(q.get("question_text", "")).strip()
        if not q_text:
            continue

        validated.append({
            "question_text":  q_text,
            "option_a":       str(q.get("option_a", "")).strip(),
            "option_b":       str(q.get("option_b", "")).strip(),
            "option_c":       str(q.get("option_c", "")).strip(),
            "option_d":       str(q.get("option_d", "")).strip(),
            "correct_answer": str(q.get("correct_answer", "")).strip().lower(),
            "explanation":    str(q.get("explanation", "")).strip(),
            "difficulty":     difficulty,
            "question_type":  question_type,
        })

    logger.info("AI Question Generator: %d valid questions returned.", len(validated))
    return validated
