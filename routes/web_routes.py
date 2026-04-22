from flask import Blueprint, render_template

bp = Blueprint('web', __name__)

@bp.route('/')
def index():
    return render_template('landing.html')

@bp.route('/onboarding')
def onboarding():
    return render_template('onboarding.html')

@bp.route('/dashboard')
def dashboard():
    return render_template('profile.html')

@bp.route('/opportunities')
def opportunities():
    return render_template('opportunities.html')

@bp.route('/company/<int:opp_id>')
def company(opp_id):
    return render_template('company.html', opp_id=opp_id)


@bp.route('/application/<int:opp_id>')
def application(opp_id):
    return render_template('application.html', opp_id=opp_id)

@bp.route('/cold_email/<int:opp_id>')
def cold_email(opp_id):
    return render_template('cold_email.html', opp_id=opp_id)

@bp.route('/analytics')
def analytics():
    return render_template('analytics.html')
