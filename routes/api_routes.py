from flask import Blueprint, request, jsonify
from database import get_db_connection
from services.phase1_onboarding import handle_onboarding_step, synthesize_profile
from services.phase2_opportunities import search_opportunities, process_approval
from services.phase3_company_intel import generate_company_report

bp = Blueprint('api', __name__, url_prefix='/api')

@bp.route('/onboarding/step', methods=['POST'])
def onboarding_step():
    data = request.json
    step = data.get('step')
    user_input = data.get('input')
    user_id = data.get('user_id', 1)
    
    response = handle_onboarding_step(user_id, step, user_input)
    return jsonify({"response": response})

@bp.route('/onboarding/synthesize', methods=['POST'])
def synthesize():
    data = request.json
    user_id = data.get('user_id', 1)
    
    profile = synthesize_profile(user_id)
    return jsonify({"profile": profile})

@bp.route('/opportunities/search', methods=['POST'])
def search_opps():
    data = request.json
    user_id = data.get('user_id', 1)
    
    results = search_opportunities(user_id)
    return jsonify({"opportunities": results})

@bp.route('/opportunities/approve', methods=['POST'])
def approve_opp():
    data = request.json
    opp_id = data.get('opportunity_id')
    decision = data.get('decision')
    
    process_approval(opp_id, decision)
    return jsonify({"status": "success"})

@bp.route('/company/report/<int:opp_id>', methods=['GET'])
def company_report(opp_id):
    report = generate_company_report(opp_id)
    return jsonify({"report": report})

@bp.route('/email/draft/<int:opp_id>', methods=['POST'])
def generate_email_draft(opp_id):
    data = request.json or {}
    user_id = data.get('user_id', 1)
    designation = data.get('designation', 'Software Engineering Intern')
    
    from services.phase4_email import draft_personalized_email
    draft = draft_personalized_email(user_id, opp_id, designation)
    return jsonify({"draft": draft})
