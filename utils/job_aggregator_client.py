"""
utils/job_aggregator_client.py
----------------------------------
Replaces theirstack_client.py with a multi-source aggregator that covers
ALL domains (tech, finance, marketing, design, research, etc.)

APIs Used (all free tier):
──────────────────────────────────────────────────────────────────────────────
1. JSearch  (RapidAPI)  – PRIMARY
   Aggregates: LinkedIn · Indeed · Glassdoor · ZipRecruiter · more
   Free tier : 500 requests / month
   Sign up   : https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
   Add to .env: JSEARCH_API_KEY=<your_rapidapi_key>

2. Adzuna              – SECONDARY (great India coverage)
   Free tier : 250 requests / day
   Sign up   : https://developer.adzuna.com/
   Add to .env: ADZUNA_APP_ID=<id>  ADZUNA_APP_KEY=<key>

3. Remotive            – TERTIARY (remote jobs, no key needed)
   Free tier : Unlimited (public API)
   Covers    : tech, marketing, design, finance, customer support, sales…
   No signup required — works out of the box.

Installation:
    pip install requests python-dotenv
    (requests is already in your requirements.txt)
──────────────────────────────────────────────────────────────────────────────
"""

import os
import re
import requests
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

JSEARCH_API_KEY = os.getenv("JSEARCH_API_KEY", "")
ADZUNA_APP_ID   = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY  = os.getenv("ADZUNA_APP_KEY", "")

# ─── Normalised job dict schema ──────────────────────────────────────────────
# Every source is normalised to this shape before returning.
# {
#   job_id, company_name, designation, location, duration,
#   stipend, apply_url, required_skills: list,
#   description_summary, source_platform, match_score, date_posted
# }

def _norm(
    job_id: str, company: str, title: str, location: str,
    salary: str, apply_url: str, skills: list,
    description: str, source: str, date_posted: str = ""
) -> dict:
    """Return a normalised job dict matching the DB schema."""
    return {
        "job_id":               str(job_id),
        "company_name":         company or "Unknown",
        "designation":          title or "N/A",
        "location":             location or "N/A",
        "duration":             None,           # filled if available
        "stipend":              salary or "Not disclosed",
        "apply_url":            apply_url or "#",
        "required_skills":      skills if isinstance(skills, list) else [],
        "description_summary":  (description or "")[:500],
        "source_platform":      source,
        "match_score":          50,             # will be recomputed in service
        "date_posted":          date_posted or "",
        "discovered_at":        None,
    }


# ─── JSearch (Primary) ───────────────────────────────────────────────────────

def _jsearch(query: str, location: Optional[str] = None, limit: int = 10, page: int = 0) -> list:
    """
    Searches LinkedIn, Indeed, Glassdoor, ZipRecruiter etc. via JSearch.
    Covers ALL job domains — not just tech.
    """
    if not JSEARCH_API_KEY:
        return []

    # JSearch pages are 1-indexed
    jsearch_page = max(1, page + 1)

    # Append location to query if provided (JSearch treats it as text)
    full_query = f"{query} {location}".strip() if location else query

    try:
        resp = requests.get(
            "https://jsearch.p.rapidapi.com/search",
            headers={
                "X-RapidAPI-Key":  JSEARCH_API_KEY,
                "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
            },
            params={
                "query":      full_query,
                "page":       str(jsearch_page),
                "num_pages":  "1",
                "date_posted":"month",
            },
            timeout=12
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except Exception as e:
        print(f"[JSearch] Error for '{query}': {e}")
        return []

    results = []
    for job in data[:limit]:
        # Build location string
        city    = job.get("job_city") or ""
        state   = job.get("job_state") or ""
        country = job.get("job_country") or ""
        is_remote = job.get("job_is_remote", False)
        loc = "Remote" if is_remote else ", ".join(p for p in [city, state, country] if p) or "N/A"

        # Build salary string
        mn = job.get("job_min_salary")
        mx = job.get("job_max_salary")
        cur = job.get("job_salary_currency") or ""
        per = job.get("job_salary_period") or ""
        salary_str = "Not disclosed"
        if mn and mx:
            salary_str = f"{cur}{int(mn):,}–{cur}{int(mx):,}/{per}"
        elif mn:
            salary_str = f"From {cur}{int(mn):,}/{per}"

        skills = job.get("job_required_skills") or []
        if not isinstance(skills, list):
            skills = []

        results.append(_norm(
            job_id       = job.get("job_id", ""),
            company      = job.get("employer_name", ""),
            title        = job.get("job_title", ""),
            location     = loc,
            salary       = salary_str,
            apply_url    = job.get("job_apply_link", "#"),
            skills       = skills,
            description  = job.get("job_description", ""),
            source       = "JSearch",
            date_posted  = (job.get("job_posted_at_datetime_utc") or "")[:10],
        ))
    return results


# ─── Adzuna (Secondary) ──────────────────────────────────────────────────────

def _adzuna(query: str, location: Optional[str] = None, limit: int = 10, page: int = 0) -> list:
    """
    Adzuna: global aggregator, excellent India coverage.
    Free: 250 req/day. Country defaults to India (in).
    """
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        return []

    # Adzuna pages are 1-indexed
    adzuna_page = max(1, page + 1)

    # Choose country based on location hint
    country = "in"  # India by default
    if location:
        loc_l = location.lower()
        if any(w in loc_l for w in ["uk", "united kingdom", "london", "manchester"]):
            country = "gb"
        elif any(w in loc_l for w in ["us", "usa", "united states", "new york", "san francisco"]):
            country = "us"

    params = {
        "app_id":           ADZUNA_APP_ID,
        "app_key":          ADZUNA_APP_KEY,
        "what":             query,
        "results_per_page": limit,
        "sort_by":          "date",
        "content-type":     "application/json",
    }
    if location:
        params["where"] = location

    try:
        resp = requests.get(
            f"https://api.adzuna.com/v1/api/jobs/{country}/search/{adzuna_page}",
            params=params,
            timeout=12
        )
        resp.raise_for_status()
        data = resp.json().get("results", [])
    except Exception as e:
        print(f"[Adzuna] Error for '{query}': {e}")
        return []

    results = []
    for job in data[:limit]:
        mn = job.get("salary_min")
        mx = job.get("salary_max")
        salary_str = "Not disclosed"
        if mn and mx:
            salary_str = f"₹{int(mn):,}–₹{int(mx):,}"
        elif mn:
            salary_str = f"From ₹{int(mn):,}"

        results.append(_norm(
            job_id      = str(job.get("id", "")),
            company     = job.get("company", {}).get("display_name", ""),
            title       = job.get("title", ""),
            location    = job.get("location", {}).get("display_name", "N/A"),
            salary      = salary_str,
            apply_url   = job.get("redirect_url", "#"),
            skills      = [],
            description = job.get("description", ""),
            source      = "Adzuna",
            date_posted = (job.get("created") or "")[:10],
        ))
    return results


# ─── Remotive (Tertiary – no API key needed) ─────────────────────────────────

# Remotive category mapping — maps domain keywords → Remotive category slugs
# Full list: https://remotive.com/api/remote-jobs/categories
_REMOTIVE_CATEGORY_MAP = {
    # Tech
    "software": "software-dev", "engineer": "software-dev", "developer": "software-dev",
    "frontend": "software-dev", "backend": "software-dev", "fullstack": "software-dev",
    "python": "software-dev", "java": "software-dev", "javascript": "software-dev",
    "ml": "software-dev", "ai": "software-dev", "machine learning": "software-dev",
    "data science": "data", "data analyst": "data", "data engineer": "data",
    "devops": "devops", "cloud": "devops", "infra": "devops",
    "cybersecurity": "security", "security": "security",
    "qa": "qa", "testing": "qa",
    "mobile": "mobile",
    # Non-tech
    "marketing": "marketing", "growth": "marketing", "seo": "marketing",
    "design": "design", "ux": "design", "ui": "design", "figma": "design",
    "finance": "finance", "accounting": "finance", "analyst": "finance",
    "product": "product", "pm": "product",
    "sales": "sales", "business development": "sales",
    "hr": "hr", "human resource": "hr", "recruiter": "hr",
    "content": "writing", "writing": "writing", "copywriting": "writing",
    "customer": "customer-support", "support": "customer-support",
}

def _remotive_category(query: str) -> Optional[str]:
    q = query.lower()
    for keyword, category in _REMOTIVE_CATEGORY_MAP.items():
        if keyword in q:
            return category
    return None  # will search without category filter

def _remotive(query: str, location: Optional[str] = None, limit: int = 10, page: int = 0) -> list:
    """
    Remotive: free public API for remote jobs across ALL domains.
    No API key needed. Works out of the box.
    Only returns remote jobs.
    """
    category = _remotive_category(query)
    params = {"search": query, "limit": limit}
    if category:
        params["category"] = category

    try:
        resp = requests.get(
            "https://remotive.com/api/remote-jobs",
            params=params,
            timeout=12
        )
        resp.raise_for_status()
        jobs = resp.json().get("jobs", [])
    except Exception as e:
        print(f"[Remotive] Error for '{query}': {e}")
        return []

    results = []
    for job in jobs[:limit]:
        # Strip HTML tags from description
        raw_desc = re.sub(r"<[^>]+>", " ", job.get("description") or "")
        raw_desc = re.sub(r"\s+", " ", raw_desc).strip()

        results.append(_norm(
            job_id      = str(job.get("id", "")),
            company     = job.get("company_name", ""),
            title       = job.get("title", ""),
            location    = "Remote",
            salary      = job.get("salary") or "Not disclosed",
            apply_url   = job.get("url", "#"),
            skills      = job.get("tags") or [],
            description = raw_desc,
            source      = "Remotive",
            date_posted = (job.get("publication_date") or "")[:10],
        ))
    return results


# ─── Public interface (same signature as old theirstack_client) ───────────────

def search_jobs(query: str, location: Optional[str] = None, limit: int = 10, page: int = 0) -> list:
    """
    Unified job search across JSearch → Adzuna → Remotive.

    Drop-in replacement for theirstack_client.search_jobs().
    Returns a list of normalised job dicts.

    Priority:
      1. JSearch  (if JSEARCH_API_KEY is set)
      2. Adzuna   (if ADZUNA_APP_ID + ADZUNA_APP_KEY are set)
      3. Remotive (always available, no key needed — remote jobs only)
    """
    results = []
    seen_keys: set = set()

    def _dedup_add(jobs: list):
        for j in jobs:
            key = j.get("job_id") or f"{j.get('company_name','')}-{j.get('designation','')}"
            if key and key not in seen_keys:
                seen_keys.add(key)
                results.append(j)

    # 1) JSearch
    jsearch_results = _jsearch(query, location, limit=limit, page=page)
    _dedup_add(jsearch_results)
    print(f"[Aggregator] JSearch returned {len(jsearch_results)} jobs for '{query}'")

    # 2) Adzuna (supplement if JSearch returned < limit)
    if len(results) < limit:
        adzuna_results = _adzuna(query, location, limit=limit - len(results), page=page)
        _dedup_add(adzuna_results)
        print(f"[Aggregator] Adzuna returned {len(adzuna_results)} jobs for '{query}'")

    # 3) Remotive (always run as remote job supplement)
    remotive_results = _remotive(query, location, limit=5, page=page)
    _dedup_add(remotive_results)
    print(f"[Aggregator] Remotive returned {len(remotive_results)} jobs for '{query}'")

    print(f"[Aggregator] Total unique jobs for '{query}': {len(results)}")
    return results