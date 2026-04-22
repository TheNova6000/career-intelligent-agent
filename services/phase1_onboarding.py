import json
from database import get_db_connection
from utils.llm_client import generate_json_response
from utils.github_client import get_github_profile

PROMPTS = {
    1: "What kind of internships are you looking for? Tell me the roles, domains, or companies you're excited about — and why. Also, what city or work mode (remote/hybrid/on-site) works for you?",
    2: "Walk me through your education — your degree, college, graduation year, and any standout scores (CGPA, JEE, board marks, SAT, etc.). Include high school too if it's notable. I'll use this to match you with companies that care about academics.",
    3: "Describe your top 2–3 projects — what problem each solved, what stack you used, and what you built. Also include any internships, part-time work, or freelance gigs if you have them.",
    4: "Share the important personal details: your full name, phone number, email, college address, and any links — LinkedIn, GitHub, portfolio, or anything else you'd like me to use."
}

def handle_onboarding_step(user_id: int, step: int, user_input: str) -> str:
    # Save user input logic goes here (mocked for now, in reality you'd parse and save piecemeal)
    
    # Return next prompt
    next_step = step + 1
    if next_step <= 4:
        return PROMPTS[next_step]
    else:
        return "Thank you! I am now synthesizing your profile..."

def synthesize_profile(user_id: int) -> dict:
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    
    # Mock gathering all the input
    github_data = get_github_profile("dummy_github") # in a real app, parse from input
    
    prompt = """
    Given the user's details, generate a structured JSON "virtual_character" with fields:
    {
      "name": "Generated User Name",
      "headline": "A passionate dev...",
      "tone": "formal",
      "core_skills": [],
      "domain_interests": [],
      "project_highlights": [],
      "writing_style_notes": "...",
      "ambition_statement": "...",
      "unique_differentiators": [],
      "academic_snapshot": "...",
      "preferred_stack": [],
      "contact_info": {}
    }
    """
    
    virtual_char = generate_json_response(prompt)
    
    conn.execute('UPDATE users SET virtual_character = ? WHERE id = ?', (json.dumps(virtual_char), user_id))
    conn.commit()
    conn.close()
    
    return virtual_char
