import json
from database import get_db_connection
from utils.llm_client import generate_json_response

def draft_personalized_email(user_id: int, opp_id: int, designation: str = "Software Engineering Intern") -> dict:
    conn = get_db_connection()
    
    # 1. Get Candidate Profile
    user = conn.execute('SELECT virtual_character FROM users WHERE id = ?', (user_id,)).fetchone()
    candidate_profile = json.loads(user['virtual_character']) if user and user['virtual_character'] else {}
    
    # 2. Get Company Intelligence
    report = conn.execute('SELECT report_data FROM company_reports WHERE opportunity_id = ? ORDER BY id DESC LIMIT 1', (opp_id,)).fetchone()
    company_intel = json.loads(report['report_data']) if report and report['report_data'] else {}
    
    conn.close()
    
    # Check if we have enough data and fallback to mock data if empty (for testing)
    if not candidate_profile:
        candidate_profile = {
            "name": "Alex Developer",
            "tone": "enthusiastic, technical, and concise",
            "skills": ["Python", "React", "AI Integration"],
            "projects": ["Built an autonomous web scraper", "Created a full-stack job board"],
            "github": "github.com/alexdev",
            "linkedin": "linkedin.com/in/alexdev"
        }
    if not company_intel:
        company_intel = {
            "what_company_does": "Building next-generation AI developer tools.",
            "future_direction": "Just raised Series A to expand their LLM orchestration platform.",
            "why_hiring": "Need engineers to scale their backend infrastructure.",
            "tech_they_care_about": ["Python", "FastAPI", "PostgreSQL", "Docker"]
        }

    # PROMPT 1: Draft Email
    draft_prompt = f"""
    You are an email-writing agent. Your job is to write a cold internship email that sounds like it was written by THIS specific person, for THIS specific company, at THIS specific moment in the company's journey.
    
    CANDIDATE: {json.dumps(candidate_profile, indent=2)}
    COMPANY: {json.dumps(company_intel, indent=2)}
    ROLE: {designation}
    
    Rules:
    - Subject line: specific, 8 words max, no "internship application"
    - Opening: reference ONE specific thing the company shipped/announced recently
    - Paragraph 2: connect candidate's most relevant project directly to the company's tech direction
    - Paragraph 3: offer something concrete (a demo, a PR, a small proof of concept)
    - Tone: match virtual_character.tone (formal/technical/warm) - default to professional yet enthusiastic if not specified.
    - Length: 180-220 words max
    - Sign-off: include GitHub + LinkedIn + one-line hook
    Do NOT use: "I am passionate", "quick learner", "team player", "would love the opportunity", or any filler phrases.
    
    Output a JSON object exactly like this:
    {{
        "subject_line": "...",
        "email_body": "...",
        "personalization_hooks_used": ["hook1", "hook2"]
    }}
    """
    
    draft_response = generate_json_response(draft_prompt)
    if not draft_response or "email_body" not in draft_response:
        return {"error": "Failed to generate initial draft"}

    # PROMPT 2: Self-Review
    review_prompt = f"""
    Review the following drafted cold email against this checklist:
    [ ] Does the opening name something SPECIFIC about the company (not generic praise)?
    [ ] Does the candidate's project clearly connect to what THIS company is building?
    [ ] Is the tone consistent with the candidate's technical profile?
    [ ] Is it under 220 words?
    [ ] Does it avoid all filler phrases ("passionate", "team player")?
    [ ] Does it end with a clear, low-pressure ask?
    
    Drafted Email:
    Subject: {draft_response.get('subject_line')}
    Body:
    {draft_response.get('email_body')}
    
    If any check fails, rewrite that section. 
    Return the final revised email + checklist results in JSON format exactly like this:
    {{
        "final_subject_line": "...",
        "final_email_body": "...",
        "hooks_used": {json.dumps(draft_response.get('personalization_hooks_used', []))},
        "checklist_passed": true,
        "improvements_made": "What was changed during review (if anything)"
    }}
    """
    
    final_response = generate_json_response(review_prompt)
    
    return final_response
