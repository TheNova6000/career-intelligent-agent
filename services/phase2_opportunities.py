"""
services/phase2_opportunities.py  — COMPLETE REWRITE
──────────────────────────────────────────────────────
Bugs fixed from original:
  1. _upsert_job() was EMPTY — every DB write silently failed
  2. Duplicate fallback block copy-pasted into load_more_opportunities()
     referenced `jobs_map` + `calls_made` which don't exist in that scope
  3. TheirStack replaced with job_aggregator_client (JSearch + Adzuna + Remotive)
     covering ALL domains — not just tech
  4. Query expansion now uses the LLM to intelligently expand vague user input
     like "AI ML beginner" into multiple precise search phrases
  5. Removed the in-function _prune_stale_opportunities closure; it's a helper now
  6. Cleaned up variable shadowing (local `jobs` re-used as both loop var and result)
"""

import json
import re
import os
from typing import Any, Dict, List, Optional

from database import get_db_connection
from utils.llm_client import generate_json_response          # already in your project
from utils.job_aggregator_client import search_jobs          # new multi-source client

# ── Config ────────────────────────────────────────────────────────────────────
MAX_EXTERNAL_CALLS = int(os.getenv("JOB_API_MAX_CALLS_PER_SEARCH", "10"))

# ── Domain expansion prompt ───────────────────────────────────────────────────
_EXPANSION_PROMPT = """You are a job search query expert. A user described what they're looking for.
Expand it into a JSON object with these exact keys:

- "search_queries": list of 4-6 precise job-title search strings (e.g. "Machine Learning Intern", "AI Research Intern entry level")
- "job_type": one of "internship" | "full_time" | "part_time" | "any"
- "experience_level": one of "entry_level" | "mid_level" | "senior_level" | "any"
- "related_skills": list of 4-6 skill keywords
- "friendly_label": short 2-4 word human label for this domain

Cover ALL relevant sub-domains, not just tech.
Respond ONLY with valid JSON — no markdown, no explanation.

Examples:
Input: "AI ML beginner"
Output: {"search_queries":["Machine Learning Intern","AI Engineer Intern entry level","Data Science Intern fresher","NLP Intern","Computer Vision Intern"],"job_type":"internship","experience_level":"entry_level","related_skills":["Python","TensorFlow","scikit-learn","NumPy","PyTorch"],"friendly_label":"AI / ML Intern"}

Input: "marketing internship"
Output: {"search_queries":["Digital Marketing Intern","Social Media Marketing Intern","Content Marketing Intern","Growth Marketing Intern","SEO Intern"],"job_type":"internship","experience_level":"entry_level","related_skills":["SEO","Google Analytics","Canva","Copywriting","Social Media"],"friendly_label":"Marketing Intern"}

Input: "finance fresher"
Output: {"search_queries":["Finance Analyst Intern","Investment Banking Intern entry level","Financial Modeling Intern","Accounting Intern fresher","FinTech Intern"],"job_type":"internship","experience_level":"entry_level","related_skills":["Excel","Financial Modeling","Accounting","Bloomberg","Python"],"friendly_label":"Finance / Analytics Intern"}

Input: """


def _expand_domain_with_llm(user_query: str) -> dict:
    """
    Use the project's existing LLM client to expand a vague domain query
    into multiple precise, searchable job titles.
    Falls back gracefully if the LLM call fails.
    """
    try:
        prompt = _EXPANSION_PROMPT + user_query
        # generate_json_response is your existing util — it returns a parsed dict
        result = generate_json_response(prompt)

        if not isinstance(result, dict):
            raise ValueError("LLM did not return a dict")

        required_keys = ["search_queries", "job_type", "experience_level", "related_skills", "friendly_label"]
        for key in required_keys:
            if key not in result:
                raise ValueError(f"Missing key: {key}")

        return result

    except Exception as e:
        print(f"[Domain Expansion] LLM failed ({e}), using rule-based fallback.")
        return _basic_expansion(user_query)


def _basic_expansion(user_query: str) -> dict:
    """Rule-based fallback when LLM is unavailable."""
    q = user_query.lower()
    is_intern = any(w in q for w in ["intern", "internship", "fresher", "beginner", "entry", "junior"])
    return {
        "search_queries": [
            f"{user_query} internship",
            f"{user_query} intern",
            f"{user_query} entry level",
            f"junior {user_query}",
            f"{user_query} fresher",
        ],
        "job_type": "internship" if is_intern else "any",
        "experience_level": "entry_level",
        "related_skills": [],
        "friendly_label": user_query.title(),
    }


# ── Match scoring ──────────────────────────────────────────────────────────────

def _compute_match_score(job: dict, virtual_char: dict) -> int:
    """Score a job 0-100 based on overlap with the user's virtual character."""
    score = int(job.get("match_score") or 50)

    if not virtual_char:
        return min(score, 100)

    # Skills overlap
    try:
        vc_skills  = {s.lower() for s in (virtual_char.get("core_skills") or [])}
        job_skills = {s.lower() for s in (job.get("required_skills") or [])}
        overlap    = len(vc_skills & job_skills)
        score     += overlap * 8
    except Exception:
        pass

    # Domain match in title/description
    try:
        domains = [d.lower() for d in (virtual_char.get("domain_interests") or [])]
        text    = ((job.get("designation") or "") + " " + (job.get("description_summary") or "")).lower()
        for d in domains:
            if d and d in text:
                score += 15
    except Exception:
        pass

    # Location preference
    try:
        pref_loc = (virtual_char.get("preferred_location") or "").lower()
        job_loc  = (job.get("location") or "").lower()
        if pref_loc and pref_loc in job_loc:
            score += 10
    except Exception:
        pass

    return min(score, 100)


# ── Query builder ──────────────────────────────────────────────────────────────

def _build_search_queries(
    char: dict,
    preferred_roles: str,
    preferred_location: Optional[str],
    user_raw_query: Optional[str] = None,
    max_queries: int = 12,
) -> list:
    """
    Build a deduplicated list of job search phrases.

    If `user_raw_query` is provided (e.g. "AI ML beginner"), it calls the LLM
    to expand it. Otherwise falls back to deriving queries from the virtual
    character profile (same logic as original, but cleaned up).
    """

    # ── Path A: LLM-based expansion for a direct user query ──────────────────
    if user_raw_query and user_raw_query.strip():
        expanded = _expand_domain_with_llm(user_raw_query.strip())
        raw_queries = expanded.get("search_queries", [])
        location_suffix = f" {preferred_location}" if preferred_location else ""
        queries = [f"{q}{location_suffix}".strip() for q in raw_queries]
        return _dedup_queries(queries, max_queries)

    # ── Path B: Profile-derived queries (original logic, cleaned) ────────────
    def _extract_list(val) -> list:
        if not val:
            return []
        if isinstance(val, list):
            return [v for v in val if v]
        return [p.strip() for p in re.split(r"[;,\n]+", str(val)) if p.strip()]

    candidates = []
    for lst in (
        _extract_list(preferred_roles),
        _extract_list(char.get("domain_interests")) if char else [],
        ([char.get("headline")] if char and char.get("headline") else []),
        _extract_list(char.get("core_skills")) if char else [],
        _extract_list(char.get("preferred_stack")) if char else [],
        _extract_list(char.get("project_highlights")) if char else [],
    ):
        for item in lst:
            if item and item not in candidates:
                candidates.append(item)

    raw_queries = []
    loc = preferred_location or ""
    for c in candidates:
        c_norm = re.sub(r"\s+", " ", str(c)).strip()
        # Use first-4-word variant for long strings
        words = c_norm.split()
        short = " ".join(words[:4]) if len(words) > 4 else c_norm
        for variant in dict.fromkeys([short, c_norm]):  # preserve order, dedup
            raw_queries.append(f"{variant} internship {loc}".strip())
            raw_queries.append(f"{variant} intern {loc}".strip())

    if not raw_queries:
        raw_queries = [f"internship {loc}".strip(), f"intern {loc}".strip()]

    return _dedup_queries(raw_queries, max_queries)


def _dedup_queries(queries: list, max_q: int) -> list:
    seen, result = set(), []
    for q in queries:
        qn = re.sub(r"\s+", " ", q).strip()
        if qn.lower() not in seen:
            seen.add(qn.lower())
            result.append(qn)
        if len(result) >= max_q:
            break
    return result


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _upsert_job(conn, user_id: int, job: Dict[str, Any], computed_score: int) -> None:
    """
    Insert or update one job in the opportunities table.
    Uses a try/except two-step (UPDATE then INSERT) for broad SQLite compatibility.
    """
    key = job.get("job_id") or f"{job.get('company_name', '')}-{job.get('designation', '')}"
    if not key:
        return

    skills_json  = json.dumps(job.get("required_skills") or [])
    source       = job.get("source_platform") or "external"
    score        = int(computed_score or job.get("match_score") or 50)

    try:
        # Attempt atomic upsert (SQLite ≥ 3.24)
        conn.execute(
            """
            INSERT INTO opportunities
                (user_id, job_id, company_name, designation, location, duration,
                 stipend, apply_url, required_skills, description_summary,
                 source_platform, match_score, date_posted, discovered_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, job_id, source_platform) DO UPDATE SET
                company_name        = excluded.company_name,
                designation         = excluded.designation,
                location            = excluded.location,
                stipend             = excluded.stipend,
                apply_url           = excluded.apply_url,
                required_skills     = excluded.required_skills,
                description_summary = excluded.description_summary,
                match_score         = MAX(opportunities.match_score, excluded.match_score),
                date_posted         = COALESCE(excluded.date_posted, opportunities.date_posted),
                updated_at          = CURRENT_TIMESTAMP,
                status              = 'pending'
            """,
            (
                user_id, key,
                job.get("company_name"),    job.get("designation"),
                job.get("location"),        job.get("duration"),
                job.get("stipend"),         job.get("apply_url"),
                skills_json,               job.get("description_summary"),
                source, score,
                job.get("date_posted"),     job.get("discovered_at"),
            ),
        )
    except Exception:
        # Fallback two-step for older SQLite versions
        conn.execute(
            """
            UPDATE opportunities SET
                company_name        = ?, designation     = ?, location     = ?,
                stipend             = ?, apply_url       = ?, required_skills = ?,
                description_summary = ?, match_score     = MAX(match_score, ?),
                date_posted         = COALESCE(?, date_posted),
                updated_at          = CURRENT_TIMESTAMP, status = 'pending'
            WHERE user_id = ? AND job_id = ? AND source_platform = ?
            """,
            (
                job.get("company_name"),    job.get("designation"),
                job.get("location"),        job.get("stipend"),
                job.get("apply_url"),       skills_json,
                job.get("description_summary"), score,
                job.get("date_posted"),     user_id, key, source,
            ),
        )
        if conn.total_changes == 0:
            conn.execute(
                """
                INSERT INTO opportunities
                    (user_id, job_id, company_name, designation, location, duration,
                     stipend, apply_url, required_skills, description_summary,
                     source_platform, match_score, date_posted, discovered_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    user_id, key,
                    job.get("company_name"),    job.get("designation"),
                    job.get("location"),        job.get("duration"),
                    job.get("stipend"),         job.get("apply_url"),
                    skills_json,               job.get("description_summary"),
                    source, score,
                    job.get("date_posted"),     job.get("discovered_at"),
                ),
            )


def _prune_stale_opportunities(conn, user_id: int, days: int = 30) -> None:
    """Mark opportunities older than `days` as expired."""
    try:
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        conn.execute(
            "UPDATE opportunities SET status = 'expired' "
            "WHERE user_id = ? AND status = 'pending' "
            "AND date(COALESCE(date_posted, created_at)) <= ?",
            (user_id, cutoff),
        )
        conn.commit()
    except Exception:
        pass


def _pending_jobs_from_db(conn, user_id: int) -> List[dict]:
    """Return all pending jobs for a user, sorted by match_score DESC."""
    rows = conn.execute(
        "SELECT * FROM opportunities WHERE user_id = ? AND status = 'pending' ORDER BY match_score DESC",
        (user_id,),
    ).fetchall()
    result = []
    for row in rows:
        r = dict(row)
        try:
            r["required_skills"] = json.loads(r.get("required_skills") or "[]")
        except Exception:
            r["required_skills"] = []
        result.append(r)
    return result


# ── Public API ─────────────────────────────────────────────────────────────────

def search_opportunities(user_id: int, user_raw_query: Optional[str] = None) -> List[dict]:
    """
    Phase 2 main function.

    1. Builds smart search queries (LLM-expanded if user_raw_query is given,
       otherwise profile-derived).
    2. Fetches from JSearch → Adzuna → Remotive (all free APIs).
    3. Scores, deduplicates, upserts to DB, and returns pending jobs.

    Parameters
    ----------
    user_id       : authenticated user's DB id
    user_raw_query: optional direct query from the UI ("AI ML beginner") —
                    if provided, LLM expansion is used instead of profile queries.
    """
    conn = get_db_connection()

    # Load user profile
    user = conn.execute(
        "SELECT virtual_character, preferred_roles, preferred_location FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    char             = json.loads(user["virtual_character"]) if user and user["virtual_character"] else {}
    preferred_roles  = (user["preferred_roles"]  or "") if user else ""
    preferred_location = (user["preferred_location"] or None) if user else None

    # Prune stale results first
    _prune_stale_opportunities(conn, user_id, days=30)

    # Build queries
    queries = _build_search_queries(
        char               = char,
        preferred_roles    = preferred_roles,
        preferred_location = preferred_location,
        user_raw_query     = user_raw_query,
        max_queries        = 12,
    )
    print(f"[Phase 2] Search queries ({len(queries)}): {queries}")

    # ── Fetch + upsert ────────────────────────────────────────────────────────
    jobs_map: Dict[str, dict] = {}   # key → job dict (in-memory dedup)
    calls_made = 0

    # Pre-load existing DB jobs into jobs_map so we don't re-score them
    for row in _pending_jobs_from_db(conn, user_id):
        key = row.get("job_id") or f"{row.get('company_name','')}-{row.get('designation','')}"
        if key:
            jobs_map[key] = row

    for query in queries:
        if calls_made >= MAX_EXTERNAL_CALLS:
            print(f"[Phase 2] External API call limit ({MAX_EXTERNAL_CALLS}) reached.")
            break

        # Skip if DB already has plenty of results for this query
        q_lower = query.lower()
        db_hits = sum(
            1 for j in jobs_map.values()
            if q_lower in (j.get("designation") or "").lower()
            or q_lower in (j.get("description_summary") or "").lower()
        )
        if db_hits >= 8:
            print(f"[Phase 2] Skipping '{query}' — {db_hits} results already in DB")
            continue

        # Call the aggregator (JSearch → Adzuna → Remotive)
        fetched_jobs = search_jobs(query, preferred_location, limit=10, page=0)
        calls_made += 1

        for job in fetched_jobs:
            score = _compute_match_score(job, char)
            key = job.get("job_id") or f"{job.get('company_name','')}-{job.get('designation','')}"
            if not key:
                continue

            # Keep highest score if we've seen this job before
            if key in jobs_map:
                prev_score = int(jobs_map[key].get("match_score") or 0)
                job["match_score"] = max(prev_score, score)
            else:
                job["match_score"] = score

            jobs_map[key] = job

            try:
                _upsert_job(conn, user_id, job, job["match_score"])
            except Exception as e:
                print(f"[Phase 2] Upsert error for '{key}': {e}")

    # ── Broad fallback if nothing found ──────────────────────────────────────
    if len(jobs_map) == 0:
        print("[Phase 2] No results found, trying broad fallback queries...")
        fallback_queries: List[str] = []
        if preferred_location:
            fallback_queries.append(f"internship {preferred_location}")
        for role in re.split(r"[;,\n]+", preferred_roles)[:2]:
            role = role.strip()
            if role:
                fallback_queries.append(f"{role} internship")
        fallback_queries.extend(["internship", "intern remote"])

        for fq in _dedup_queries(fallback_queries, max_q=4):
            if calls_made >= MAX_EXTERNAL_CALLS + 3:
                break
            fetched_jobs = search_jobs(fq, preferred_location, limit=10, page=0)
            calls_made += 1
            for job in fetched_jobs:
                score = _compute_match_score(job, char)
                key = job.get("job_id") or f"{job.get('company_name','')}-{job.get('designation','')}"
                if not key or key in jobs_map:
                    continue
                job["match_score"] = score
                jobs_map[key] = job
                try:
                    _upsert_job(conn, user_id, job, score)
                except Exception as e:
                    print(f"[Phase 2 fallback] Upsert error: {e}")

    try:
        conn.commit()
    except Exception:
        pass

    # Return all pending jobs from DB (includes previously approved + newly fetched)
    result = _pending_jobs_from_db(conn, user_id)
    conn.close()
    print(f"[Phase 2] Returning {len(result)} pending opportunities.")
    return result


def load_more_opportunities(user_id: int, page: int = 1, per_page: int = 10) -> List[dict]:
    """
    Fetch the next page of results from the API for all profile-derived queries.
    Called when the user scrolls / requests more results in the UI.
    """
    conn = get_db_connection()
    user = conn.execute(
        "SELECT virtual_character, preferred_roles, preferred_location FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    char             = json.loads(user["virtual_character"]) if user and user["virtual_character"] else {}
    preferred_roles  = (user["preferred_roles"]  or "") if user else ""
    preferred_location = (user["preferred_location"] or None) if user else None

    queries = _build_search_queries(char, preferred_roles, preferred_location, max_queries=12)

    for query in queries:
        fetched_jobs = search_jobs(query, preferred_location, limit=per_page, page=page)
        for job in fetched_jobs:
            try:
                score = _compute_match_score(job, char)
                job["match_score"] = score
                _upsert_job(conn, user_id, job, score)
            except Exception as e:
                print(f"[load_more] Error for job: {e}")

    try:
        conn.commit()
    except Exception:
        pass
    conn.close()


def process_approval(opp_id: int, decision: str) -> None:
    """Update opportunity status based on user's swipe decision."""
    status_map = {
        "y": "approved", "yes": "approved",
        "n": "rejected",  "no":  "rejected",
    }
    status = status_map.get(decision.strip().lower(), "pending")
    conn = get_db_connection()
    conn.execute("UPDATE opportunities SET status = ? WHERE id = ?", (status, opp_id))
    conn.commit()
    conn.close()