import json
import re
from database import get_db_connection
from utils.llm_client import generate_json_response
from utils.github_client import get_github_profile

PROMPTS = {
    1: "What kind of internships are you looking for? Tell me the roles, domains, or companies you're excited about — and why. Also, what city or work mode (remote/hybrid/on-site) works for you?",
    2: "Walk me through your education — your degree, college, graduation year, and any standout scores (CGPA, JEE, board marks, SAT, etc.). Include high school too if it's notable. I'll use this to match you with companies that care about academics.",
    3: "Describe your top 2–3 projects — what problem each solved, what stack you used, and what you built. Also include any internships, part-time work, or freelance gigs if you have them.",
    4: "Share the important personal details: your full name, phone number, email, college address, and any links — LinkedIn, GitHub, portfolio, or anything else you'd like me to use."
}


def _ensure_user_exists(conn, user_id: int):
    row = conn.execute('SELECT id FROM users WHERE id = ?', (user_id,)).fetchone()
    if not row:
        conn.execute('INSERT OR IGNORE INTO users (id) VALUES (?)', (user_id,))
        conn.commit()


def handle_onboarding_step(user_id: int, step: int, user_input: str) -> str:
    conn = get_db_connection()
    _ensure_user_exists(conn, user_id)

    user_input = (user_input or "").strip()

    if step == 1:
        # store user's role/location preferences
        location = None
        if re.search(r'\bremote\b', user_input, re.I):
            location = 'Remote'
        elif re.search(r'\bhybrid\b', user_input, re.I):
            location = 'Hybrid'

        conn.execute('UPDATE users SET preferred_roles = ?, preferred_location = ? WHERE id = ?', (user_input or None, location, user_id))

    elif step == 2:
        # store education details
        conn.execute('UPDATE users SET degree = ? WHERE id = ?', (user_input or None, user_id))

    elif step == 3:
        # store projects / tech stack notes
        conn.execute('UPDATE users SET preferred_stack = ? WHERE id = ?', (user_input or None, user_id))

    elif step == 4:
        # try to extract name, email, phone and github username
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', user_input)
        phone_match = re.search(r'(\+?\d[\d\-\s]{7,}\d)', user_input)

        name = None
        lines = [l.strip() for l in user_input.splitlines() if l.strip()]
        if lines:
            for l in lines:
                if '@' not in l and 'github.com' not in l and re.search(r'[A-Za-z]', l):
                    name = l
                    break

        conn.execute('UPDATE users SET name = ?, email = ?, phone = ? WHERE id = ?', (name, email_match.group(0) if email_match else None, phone_match.group(0) if phone_match else None, user_id))

        gh_username = None
        gh_match = re.search(r'github\.com/([A-Za-z0-9_-]+)', user_input)
        if gh_match:
            gh_username = gh_match.group(1)
            conn.execute('INSERT INTO github_data (user_id, username, extracted_data) VALUES (?, ?, ?)', (user_id, gh_username, json.dumps({})))

    conn.commit()
    conn.close()

    # return next prompt
    next_step = step + 1
    if next_step <= 4:
        return PROMPTS[next_step]
    else:
        return "Thank you! I am now synthesizing your profile..."


def synthesize_profile(user_id: int, force: bool = False) -> dict:
    """Create or return a user's virtual_character.

    By default (`force=False`) this will not call the LLM and will return a
    stored `virtual_character` if present or synthesize a minimal profile from
    stored onboarding fields. Set `force=True` to call the LLM and overwrite
    the stored profile.
    """
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        conn.close()
        return {}

    # If a profile already exists and we are not forcing an LLM call, return it
    existing = user['virtual_character']
    if existing and not force:
        try:
            parsed = json.loads(existing)
            # If nested under 'virtual_character', return its value
            if isinstance(parsed, dict) and 'virtual_character' in parsed and isinstance(parsed['virtual_character'], dict):
                conn.close()
                return parsed['virtual_character']
            conn.close()
            return parsed
        except Exception:
            # fall through to synthesizing from stored fields
            pass

    user_data = {
        'name': user['name'],
        'email': user['email'],
        'phone': user['phone'],
        'college': user['college'],
        'degree': user['degree'],
        'grad_year': user['grad_year'],
        'gpa': user['gpa'],
        'preferred_location': user['preferred_location'],
        'preferred_roles': user['preferred_roles'],
        'preferred_stack': user['preferred_stack']
    }

    gh_row = conn.execute('SELECT username FROM github_data WHERE user_id = ?', (user_id,)).fetchone()
    github_username = gh_row['username'] if gh_row else None
    github_data = {}
    if github_username:
        github_data = get_github_profile(github_username) or {}

    # If not forcing LLM, build a lightweight profile from onboarding fields
    if not force:
        vc = {
            'name': user_data.get('name') or 'Candidate',
            'headline': f"{(user_data.get('degree') or '').strip()} candidate" if user_data.get('degree') else 'Candidate',
            'tone': 'professional',
            'core_skills': [s.strip() for s in (user_data.get('preferred_stack') or '').split(',') if s.strip()],
            'domain_interests': [d.strip() for d in (user_data.get('preferred_roles') or '').split(',') if d.strip()],
            'project_highlights': [],
            'writing_style_notes': '',
            'ambition_statement': '',
            'unique_differentiators': [],
            'academic_snapshot': user_data.get('degree'),
            'preferred_stack': [s.strip() for s in (user_data.get('preferred_stack') or '').split(',') if s.strip()],
            'contact_info': {'email': user_data.get('email'), 'phone': user_data.get('phone')}
        }
        virtual_char = vc
        conn.execute('UPDATE users SET virtual_character = ? WHERE id = ?', (json.dumps(virtual_char), user_id))
        conn.commit()
        conn.close()
        return virtual_char

    # force==True -> call LLM and update stored profile
    prompt = f"""
    You are a job-matching assistant. Given the following raw user data, generate a structured JSON object named "virtual_character" with the fields:
    name, headline, tone, core_skills (list), domain_interests (list), project_highlights (list of strings), writing_style_notes, ambition_statement, unique_differentiators (list), academic_snapshot, preferred_stack (list), contact_info (object)
    Keep domain_interests consistent with user's preferred_roles; prefer marketing/ads/product roles if preferred_roles mention marketing.
    Raw user data: {json.dumps(user_data)}
    GitHub summary: {json.dumps(github_data)}
    Return ONLY valid JSON.
    """

    virtual_char_response = generate_json_response(prompt)

    # Normalize response: accept both { ... } and { "virtual_character": { ... } }
    if not virtual_char_response:
        virtual_char = {
            'name': user_data.get('name') or 'Candidate',
            'headline': (user_data.get('degree') or '') + ' candidate',
            'tone': 'professional',
            'core_skills': [s.strip() for s in (user_data.get('preferred_stack') or '').split(',') if s.strip()],
            'domain_interests': [d.strip() for d in (user_data.get('preferred_roles') or '').split(',') if d.strip()],
            'project_highlights': [],
            'writing_style_notes': '',
            'ambition_statement': '',
            'unique_differentiators': [],
            'academic_snapshot': user_data.get('degree'),
            'preferred_stack': [s.strip() for s in (user_data.get('preferred_stack') or '').split(',') if s.strip()],
            'contact_info': {'email': user_data.get('email'), 'phone': user_data.get('phone')}
        }
    else:
        if isinstance(virtual_char_response, dict) and 'virtual_character' in virtual_char_response and isinstance(virtual_char_response['virtual_character'], dict):
            virtual_char = virtual_char_response['virtual_character']
        else:
            virtual_char = virtual_char_response

    conn.execute('UPDATE users SET virtual_character = ? WHERE id = ?', (json.dumps(virtual_char), user_id))
    conn.commit()
    conn.close()

    return virtual_char
