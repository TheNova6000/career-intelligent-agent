import os
import requests
from typing import List, Dict, Optional

THEIRSTACK_API_KEY = os.getenv('THEIRSTACK_API_KEY')
THEIRSTACK_BASE_URL = os.getenv('THEIRSTACK_BASE_URL', 'https://api.theirstack.com')
import os
import time
import requests
from typing import List, Dict, Optional, Tuple

THEIRSTACK_API_KEY = os.getenv('THEIRSTACK_API_KEY')
THEIRSTACK_BASE_URL = os.getenv('THEIRSTACK_BASE_URL', 'https://api.theirstack.com')


def _extract_rate_headers(resp) -> Dict[str, str]:
    headers = {}
    try:
        for k in ('RateLimit', 'RateLimit-Policy', 'RateLimit-Limit', 'RateLimit-Remaining', 'RateLimit-Reset'):
            if k in resp.headers:
                headers[k] = resp.headers.get(k)
    except Exception:
        pass
    return headers


def search_jobs(keywords: str, location: Optional[str] = None, limit: int = 50, page: int = 0) -> Tuple[List[Dict], Dict[str, str]]:
    """Search jobs via TheirStack and normalize results to our schema.

    Returns a tuple `(jobs_list, headers_dict)`. The headers dict contains
    rate-limit information (if provided). On failure, returns ([], {}).
    """
    if not THEIRSTACK_API_KEY:
        print("THEIRSTACK_API_KEY not set; skipping TheirStack fetch.")
        return [], {}

    url = f"{THEIRSTACK_BASE_URL}/v1/jobs/search"
    headers = {
        'Authorization': f'Bearer {THEIRSTACK_API_KEY}',
        'Content-Type': 'application/json'
    }

    payload = {
        'page': int(page or 0),
        'limit': int(limit or 50),
        # require a time filter to satisfy TheirStack API requirements
        'posted_at_max_age_days': 30
    }

    if keywords:
        payload['job_title_or'] = [keywords]

    if location:
        loc = str(location).strip()
        if len(loc) == 2 and loc.isalpha():
            payload['job_country_code_or'] = [loc.upper()]
        elif 'remote' in loc.lower():
            payload['remote'] = True

    attempts = 3
    backoff = 1.0
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 429:
                # rate limited: honor Retry-After if present or backoff
                retry_after = resp.headers.get('Retry-After')
                wait = float(retry_after) if retry_after and retry_after.isdigit() else backoff
                print(f"TheirStack rate limited (429). Waiting {wait}s before retrying.")
                time.sleep(wait)
                backoff *= 2
                continue
            resp.raise_for_status()
            data = resp.json()

            raw_jobs = data.get('data') if isinstance(data, dict) else []
            normalized = []
            for j in raw_jobs:
                company_name = j.get('company') or (j.get('company_object') or {}).get('name') or j.get('company_name')
                required_skills = j.get('technology_slugs') or j.get('keyword_slugs') or j.get('technology_names') or []
                if isinstance(required_skills, list):
                    req_skills = required_skills
                else:
                    req_skills = [required_skills] if required_skills else []

                normalized.append({
                    'job_id': str(j.get('id') or j.get('job_id') or ''),
                    'company_name': company_name,
                    'designation': j.get('job_title') or j.get('title') or j.get('designation') or '',
                    'location': j.get('location') or j.get('short_location') or j.get('long_location') or (location or ''),
                    'duration': j.get('duration') or '',
                    'stipend': j.get('salary') or j.get('min_annual_salary') or j.get('salary_string') or '',
                    'apply_url': j.get('final_url') or j.get('url') or j.get('source_url') or '',
                    'required_skills': req_skills,
                    'description_summary': j.get('description') or j.get('summary') or '',
                    'date_posted': j.get('date_posted') or j.get('date_posted_utc') or None,
                    'discovered_at': j.get('discovered_at') or None,
                    'source_platform': 'theirstack',
                    'match_score': j.get('score') or j.get('match_score') or 50
                })

            rate_headers = _extract_rate_headers(resp)
            return normalized, rate_headers

        except requests.exceptions.RequestException as e:
            print(f"TheirStack request attempt {attempt} failed: {e}")
            if attempt < attempts:
                time.sleep(backoff)
                backoff *= 2
                continue
            return [], {}
        except Exception as e:
            print(f"Error parsing TheirStack response: {e}")
            return [], {}
