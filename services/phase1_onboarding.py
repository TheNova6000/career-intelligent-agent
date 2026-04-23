import json
import re

from database import get_db_connection
from utils.github_client import get_github_profile
from utils.llm_client import generate_json_response

PROMPTS = {
    1: "What kind of internships are you looking for? Tell me the roles, domains, or companies you're excited about and why. Also, what city or work mode (remote/hybrid/on-site) works for you?",
    2: "Describe your top 2-3 projects, your technical skills, the stack you used, and anything else you have built. Include internships, freelance work, certifications, or notable hands-on experience too.",
    3: "Walk me through your education: college, degree, graduation year, GPA or marks, and any standout academic achievements that matter for internships.",
    4: "Share your GitHub, LinkedIn, portfolio, resume link, and any important contact details like your full name, phone number, and email."
}


def _ensure_user_exists(conn, user_id: int):
    row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        conn.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (user_id,))
        conn.commit()


def handle_onboarding_step(user_id: int, step: int, user_input: str) -> str:
    conn = get_db_connection()
    _ensure_user_exists(conn, user_id)

    user_input = (user_input or "").strip()

    if step == 1:
        location = None
        if re.search(r"\bremote\b", user_input, re.I):
            location = "Remote"
        elif re.search(r"\bhybrid\b", user_input, re.I):
            location = "Hybrid"
        elif re.search(r"\bon[-\s]?site\b", user_input, re.I):
            location = "On-site"

        conn.execute(
            "UPDATE users SET preferred_roles = ?, preferred_location = ? WHERE id = ?",
            (user_input or None, location, user_id),
        )

    elif step == 2:
        conn.execute(
            "UPDATE users SET preferred_stack = ? WHERE id = ?",
            (user_input or None, user_id),
        )

    elif step == 3:
        conn.execute(
            "UPDATE users SET degree = ? WHERE id = ?",
            (user_input or None, user_id),
        )

    elif step == 4:
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", user_input)
        phone_match = re.search(r"(\+?\d[\d\-\s]{7,}\d)", user_input)

        name = None
        lines = [line.strip() for line in user_input.splitlines() if line.strip()]
        for line in lines:
            if "@" not in line and "github.com" not in line and re.search(r"[A-Za-z]", line):
                name = line
                break

        email_value = email_match.group(0) if email_match else None
        phone_value = phone_match.group(0) if phone_match else None

        if email_value:
            existing_email_owner = conn.execute(
                "SELECT id FROM users WHERE email = ? AND id != ?",
                (email_value, user_id),
            ).fetchone()
            if existing_email_owner:
                email_value = None

        conn.execute(
            "UPDATE users SET name = COALESCE(?, name), email = COALESCE(?, email), phone = COALESCE(?, phone) WHERE id = ?",
            (name, email_value, phone_value, user_id),
        )

        gh_match = re.search(r"github\.com/([A-Za-z0-9_-]+)", user_input, re.I)
        if gh_match:
            gh_username = gh_match.group(1)
            existing_github = conn.execute(
                "SELECT user_id FROM github_data WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if existing_github:
                conn.execute(
                    "UPDATE github_data SET username = ?, extracted_data = ? WHERE user_id = ?",
                    (gh_username, json.dumps({}), user_id),
                )
            else:
                conn.execute(
                    "INSERT INTO github_data (user_id, username, extracted_data) VALUES (?, ?, ?)",
                    (user_id, gh_username, json.dumps({})),
                )

    conn.commit()
    conn.close()

    next_step = step + 1
    if next_step <= 4:
        return PROMPTS[next_step]
    return "Thank you! I am now synthesizing your profile..."


def synthesize_profile(user_id: int, force: bool = False) -> dict:
    """Create or return a user's virtual_character."""
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        conn.close()
        return {}

    existing = user["virtual_character"]
    if existing and not force:
        try:
            parsed = json.loads(existing)
            if (
                isinstance(parsed, dict)
                and "virtual_character" in parsed
                and isinstance(parsed["virtual_character"], dict)
            ):
                conn.close()
                return parsed["virtual_character"]
            conn.close()
            return parsed
        except Exception:
            pass

    user_data = {
        "name": user["name"],
        "email": user["email"],
        "phone": user["phone"],
        "college": user["college"],
        "degree": user["degree"],
        "grad_year": user["grad_year"],
        "gpa": user["gpa"],
        "preferred_location": user["preferred_location"],
        "preferred_roles": user["preferred_roles"],
        "preferred_stack": user["preferred_stack"],
    }

    gh_row = conn.execute("SELECT username FROM github_data WHERE user_id = ?", (user_id,)).fetchone()
    github_username = gh_row["username"] if gh_row else None
    github_data = get_github_profile(github_username) if github_username else {}
    github_data = github_data or {}

    if not force:
        virtual_char = {
            "name": user_data.get("name") or "Candidate",
            "headline": f"{(user_data.get('degree') or '').strip()} candidate" if user_data.get("degree") else "Candidate",
            "tone": "professional",
            "core_skills": [s.strip() for s in (user_data.get("preferred_stack") or "").split(",") if s.strip()],
            "domain_interests": [d.strip() for d in (user_data.get("preferred_roles") or "").split(",") if d.strip()],
            "project_highlights": [],
            "writing_style_notes": "",
            "ambition_statement": "",
            "unique_differentiators": [],
            "academic_snapshot": user_data.get("degree"),
            "preferred_stack": [s.strip() for s in (user_data.get("preferred_stack") or "").split(",") if s.strip()],
            "contact_info": {"email": user_data.get("email"), "phone": user_data.get("phone")},
        }
        conn.execute("UPDATE users SET virtual_character = ? WHERE id = ?", (json.dumps(virtual_char), user_id))
        conn.commit()
        conn.close()
        return virtual_char

    prompt = f"""
    You are a job-matching assistant. Given the following raw user data, generate a structured JSON object named "virtual_character" with the fields:
    name, headline, tone, core_skills (list), domain_interests (list), project_highlights (list of strings), writing_style_notes, ambition_statement, unique_differentiators (list), academic_snapshot, preferred_stack (list), contact_info (object)
    Keep domain_interests consistent with user's preferred_roles; prefer marketing/ads/product roles if preferred_roles mention marketing.
    Raw user data: {json.dumps(user_data)}
    GitHub summary: {json.dumps(github_data)}
    Return ONLY valid JSON.
    """

    virtual_char_response = generate_json_response(prompt)

    if not virtual_char_response:
        virtual_char = {
            "name": user_data.get("name") or "Candidate",
            "headline": ((user_data.get("degree") or "") + " candidate").strip() or "Candidate",
            "tone": "professional",
            "core_skills": [s.strip() for s in (user_data.get("preferred_stack") or "").split(",") if s.strip()],
            "domain_interests": [d.strip() for d in (user_data.get("preferred_roles") or "").split(",") if d.strip()],
            "project_highlights": [],
            "writing_style_notes": "",
            "ambition_statement": "",
            "unique_differentiators": [],
            "academic_snapshot": user_data.get("degree"),
            "preferred_stack": [s.strip() for s in (user_data.get("preferred_stack") or "").split(",") if s.strip()],
            "contact_info": {"email": user_data.get("email"), "phone": user_data.get("phone")},
        }
    elif (
        isinstance(virtual_char_response, dict)
        and "virtual_character" in virtual_char_response
        and isinstance(virtual_char_response["virtual_character"], dict)
    ):
        virtual_char = virtual_char_response["virtual_character"]
    else:
        virtual_char = virtual_char_response

    conn.execute("UPDATE users SET virtual_character = ? WHERE id = ?", (json.dumps(virtual_char), user_id))
    conn.commit()
    conn.close()

    return virtual_char
