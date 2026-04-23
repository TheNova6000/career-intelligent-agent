from flask import Blueprint, render_template, session, redirect, url_for

bp = Blueprint('web', __name__)


def _create_session_user():
    from database import get_db_connection

    conn = get_db_connection()
    cursor = conn.execute('''
        INSERT INTO users (name, email, phone, college, degree, grad_year, gpa,
                         preferred_location, preferred_roles, preferred_stack, virtual_character)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        'New User',
        f'newuser_{int(__import__("time").time())}@example.com',
        '', '', '', '', '', '', '', '', '{}'
    ))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    session['user_id'] = user_id
    return user_id

@bp.route('/')
def index():
    return render_template('landing.html')

@bp.route('/login')
def login():
    _create_session_user()
    return redirect(url_for('web.dashboard'))

@bp.route('/onboarding')
def onboarding():
    if not session.get('user_id'):
        _create_session_user()
    return render_template('onboarding.html')

@bp.route('/dashboard')
def dashboard():
    # Display user dashboard with list of users
    from database import get_db_connection
    conn = get_db_connection()
    users = conn.execute('SELECT id, name, email, created_at FROM users ORDER BY created_at DESC').fetchall()
    conn.close()
    users_list = [dict(user) for user in users]
    return render_template('dashboard.html', users=users_list, current_user_id=session.get('user_id'))

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
