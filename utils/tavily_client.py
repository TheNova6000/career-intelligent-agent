import os
import time
import requests
from typing import List, Dict, Optional

TAVILY_API_KEY = os.getenv('TAVILY_API_KEY')
TAVILY_BASE_URL = os.getenv('TAVILY_BASE_URL', 'https://api.tavily.ai/v1')


def search_jobs(keywords: str, location: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """Search jobs via the TAVILY API with retries and tolerant parsing.

    Returns a list of normalized job dicts. On network/DNS failures this will
    retry a few times and then return an empty list. This function is defensive
    because network resolution problems are environment-specific.
    """
    if not TAVILY_API_KEY:
        print("TAVILY_API_KEY not set; cannot fetch jobs from TAVILY.")
        return []

    url = f"{TAVILY_BASE_URL}/jobs/search"
    headers = {
        'Authorization': f'Bearer {TAVILY_API_KEY}',
        'Content-Type': 'application/json'
    }

    payload = {
        'query': keywords,
        'location': location,
        'limit': limit
    }

    attempts = 3
    backoff = 1.0
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            resp.raise_for_status()
            data = resp.json()

            # Tolerant parsing: accept {"jobs": [...] } or a top-level list
            raw_jobs = data.get('jobs') if isinstance(data, dict) and 'jobs' in data else (data if isinstance(data, list) else [])

            normalized = []
            for j in raw_jobs:
                normalized.append({
                    'job_id': str(j.get('id') or j.get('job_id') or j.get('reference') or ''),
                    'company_name': j.get('company') or j.get('company_name') or j.get('employer', ''),
                    'designation': j.get('title') or j.get('designation') or j.get('role', ''),
                    'location': j.get('location') or j.get('city') or location or '',
                    'duration': j.get('duration', ''),
                    'stipend': j.get('salary') or j.get('compensation', ''),
                    'apply_url': j.get('apply_url') or j.get('url') or j.get('redirect', ''),
                    'required_skills': j.get('skills') or j.get('required_skills') or [],
                    'description_summary': j.get('summary') or j.get('description') or '',
                    'date_posted': j.get('date_posted') or j.get('date') or None,
                    'discovered_at': j.get('discovered_at') or None,
                    'source_platform': j.get('source') or 'tavily',
                    'match_score': j.get('score') or j.get('match_score') or 50
                })

            return normalized

        except requests.exceptions.RequestException as e:
            # Network/DNS issues or timeouts
            err_str = str(e)
            print(f"TAVILY request attempt {attempt} failed: {err_str}")
            if attempt < attempts:
                time.sleep(backoff)
                backoff *= 2
                continue
            else:
                print("TAVILY fetch ultimately failed after retries; returning [].")
                return []
        except Exception as e:
            print(f"Error parsing TAVILY response: {e}")
            return []
