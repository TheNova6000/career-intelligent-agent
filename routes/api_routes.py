"""
routes/api_routes.py  (Phase 2 section - add/replace these endpoints)
Adds one new endpoint: POST /api/opportunities/search-domain
  -> Accepts a raw user query ("AI ML beginner") and calls Phase 2
     with LLM-based expansion.

The original endpoint POST /api/opportunities/fetch can remain and now
also accepts an optional `query` field.
"""

from flask import Blueprint, request, jsonify, session
from services.phase1_onboarding import handle_onboarding_step, synthesize_profile
from services.phase3_company_intel import generate_company_report
from services.phase2_opportunities import (
    search_opportunities,
    load_more_opportunities,
    process_approval,
)

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/opportunities", methods=["GET"])
def get_opportunities():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    jobs = search_opportunities(user_id)
    return jsonify({"opportunities": jobs, "count": len(jobs)}), 200


@api_bp.route("/opportunities/search-domain", methods=["POST"])
def search_domain():
    """
    POST /api/opportunities/search-domain
    Body: { "query": "AI ML beginner" }

    Uses LLM expansion to find relevant internships across ALL domains.
    Returns same schema as GET /api/opportunities.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    body = request.get_json(force=True) or {}
    query = (body.get("query") or "").strip()

    if not query:
        return jsonify({"error": "query field is required"}), 400

    jobs = search_opportunities(user_id, user_raw_query=query)
    return jsonify({"opportunities": jobs, "count": len(jobs), "query": query}), 200


@api_bp.route("/opportunities/search", methods=["POST"])
def search_opportunities_compat():
    """
    Backward-compatible search endpoint used by the current opportunities UI.
    Ignores any posted user_id and always uses the active session user.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    body = request.get_json(force=True) or {}
    query = (body.get("query") or "").strip()

    if query:
        jobs = search_opportunities(user_id, user_raw_query=query)
    else:
        jobs = search_opportunities(user_id)

    return jsonify({"opportunities": jobs, "count": len(jobs)}), 200


@api_bp.route("/opportunities/load-more", methods=["POST"])
def load_more():
    """
    POST /api/opportunities/load-more
    Body: { "page": 2 }

    Fetches the next page from external APIs and stores results in DB.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    body = request.get_json(force=True) or {}
    page = int(body.get("page", 1))

    load_more_opportunities(user_id, page=page)

    from services.phase2_opportunities import _pending_jobs_from_db
    from database import get_db_connection

    conn = get_db_connection()
    jobs = _pending_jobs_from_db(conn, user_id)
    conn.close()

    return jsonify({"opportunities": jobs, "count": len(jobs), "page": page}), 200


@api_bp.route("/opportunities/<int:opp_id>/decision", methods=["POST"])
def decide_opportunity(opp_id: int):
    """
    POST /api/opportunities/<id>/decision
    Body: { "decision": "yes" } or { "decision": "no" }
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    body = request.get_json(force=True) or {}
    decision = body.get("decision", "no")
    process_approval(opp_id, decision)

    return jsonify({"status": "ok", "opp_id": opp_id, "decision": decision}), 200


@api_bp.route("/opportunities/approve", methods=["POST"])
def approve_opportunity_compat():
    """
    Backward-compatible approval endpoint used by the current opportunities UI.
    Accepts { opportunity_id, decision } where decision may be Y/N or yes/no.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    body = request.get_json(force=True) or {}
    opp_id = body.get("opportunity_id")
    if opp_id is None:
        return jsonify({"error": "opportunity_id is required"}), 400

    raw_decision = str(body.get("decision", "N")).strip().upper()
    normalized_decision = "yes" if raw_decision in {"Y", "YES", "TRUE", "1"} else "no"
    process_approval(int(opp_id), normalized_decision)

    return jsonify({"status": "ok", "opp_id": int(opp_id), "decision": normalized_decision}), 200


@api_bp.route("/switch-user", methods=["POST"])
def switch_user():
    """Switch the current active user in the session."""
    data = request.get_json(force=True) or {}
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    from database import get_db_connection

    conn = get_db_connection()
    user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if not user:
        return jsonify({"error": "User not found"}), 404

    session["user_id"] = user_id
    return jsonify({"success": True, "user_id": user_id}), 200


@api_bp.route("/onboarding/step", methods=["POST"])
def onboarding_step():
    data = request.get_json(force=True) or {}
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    step = int(data.get("step", 1))
    user_input = (data.get("input") or "").strip()

    if step < 1 or step > 4:
        return jsonify({"error": "Invalid onboarding step"}), 400

    if not user_input:
        return jsonify({"error": "input is required"}), 400

    response_text = handle_onboarding_step(user_id, step, user_input)
    completed = step >= 4
    next_step = min(step + 1, 4)

    return jsonify(
        {
            "response": response_text,
            "step": step,
            "next_step": next_step,
            "completed": completed,
            "redirect_url": "/opportunities" if completed else None,
        }
    ), 200


@api_bp.route("/onboarding/synthesize", methods=["POST"])
def synthesize():
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    profile = synthesize_profile(user_id)
    return jsonify({"profile": profile, "redirect_url": "/opportunities"}), 200


@api_bp.route("/company/report/<int:opp_id>", methods=["GET"])
def company_report(opp_id: int):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    report = generate_company_report(opp_id)
    return jsonify({"report": report}), 200


@api_bp.route("/email/draft/<int:opp_id>", methods=["POST"])
def generate_email_draft(opp_id: int):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    data = request.get_json(force=True) or {}
    designation = data.get("designation", "Software Engineering Intern")

    from services.phase4_email import draft_personalized_email

    draft = draft_personalized_email(user_id, opp_id, designation)
    return jsonify({"draft": draft}), 200
