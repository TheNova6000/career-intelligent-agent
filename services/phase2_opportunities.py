import json
from database import get_db_connection
from utils.llm_client import generate_json_response

def search_opportunities(user_id: int) -> list:
    conn = get_db_connection()
    user = conn.execute('SELECT virtual_character FROM users WHERE id = ?', (user_id,)).fetchone()
    char = json.loads(user['virtual_character']) if user and user['virtual_character'] else {}
    
    # MOCK scraping. In reality, call a Playwright/BeautifulSoup scraper
    mock_jobs = [
        {
            "job_id": "1",
            "company_name": "Google",
            "designation": "Software Engineering Intern",
            "location": "Remote",
            "duration": "3 months",
            "stipend": "$8000/mo",
            "apply_url": "https://careers.google.com",
            "required_skills": ["Python", "C++", "Algorithms"],
            "description_summary": "Work on core search algorithms.",
            "source_platform": "LinkedIn",
            "match_score": 95
        },
        {
            "job_id": "2",
            "company_name": "Startup Inc",
            "designation": "AI Engineer Intern",
            "location": "Hybrid",
            "duration": "6 months",
            "stipend": "$4000/mo",
            "apply_url": "https://wellfound.com",
            "required_skills": ["Python", "FastAPI", "LLMs"],
            "description_summary": "Build agentic workflows.",
            "source_platform": "Wellfound",
            "match_score": 88
        }
    ]
    
    for job in mock_jobs:
        conn.execute('''
            INSERT INTO opportunities 
            (user_id, job_id, company_name, designation, location, duration, stipend, apply_url, required_skills, description_summary, source_platform, match_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, job['job_id'], job['company_name'], job['designation'], job['location'], job['duration'], job['stipend'], job['apply_url'], json.dumps(job['required_skills']), job['description_summary'], job['source_platform'], job['match_score']))
    
    conn.commit()
    
    cursor = conn.execute('SELECT * FROM opportunities WHERE user_id = ? AND status = ?', (user_id, 'pending'))
    pending_jobs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return pending_jobs

def process_approval(opp_id: int, decision: str):
    conn = get_db_connection()
    status = 'approved' if decision.lower() in ['y', 'yes'] else ('rejected' if decision.lower() in ['n', 'no'] else 'pending')
    conn.execute('UPDATE opportunities SET status = ? WHERE id = ?', (status, opp_id))
    conn.commit()
    conn.close()
