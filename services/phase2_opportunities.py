import json
import re
import os
from database import get_db_connection
from utils.llm_client import generate_json_response
from utils.theirstack_client import search_jobs as theirstack_search_jobs
from typing import Tuple, Dict, Any


def _compute_match_score(job: dict, virtual_char: dict) -> int:
    score = int(job.get('match_score', 50) or 50)

    try:
        vc_skills = [s.lower() for s in virtual_char.get('core_skills', [])] if virtual_char else []
    except Exception:
        vc_skills = []
    job_skills = [s.lower() for s in (job.get('required_skills') or [])]

    overlap = len(set(vc_skills) & set(job_skills))
    score += overlap * 8

    domains = [d.lower() for d in virtual_char.get('domain_interests', [])] if virtual_char else []
    title = (job.get('designation') or '') + ' ' + (job.get('description_summary') or '')
    title = title.lower()
    for d in domains:
        if d and d in title:
            score += 15

    # prefer location match
    try:
        pref_loc = (virtual_char.get('preferred_location') or '').lower() if virtual_char else ''
        job_loc = (job.get('location') or '').lower()
        if pref_loc and pref_loc in job_loc:
            score += 10
    except Exception:
        pass

    if score > 100:
        score = 100
    return score


def _build_search_queries(char: dict, preferred_roles: str, preferred_location: str, max_queries: int = 12) -> list:
    """Construct search queries strictly from onboarding/profile fields.

    No hardcoded role lists or negative filters are used; queries are derived
    deterministically from what the user provided in onboarding and the
    synthesized virtual character.
    """
    def _extract_list(val):
        if not val:
            return []
        if isinstance(val, list):
            return [v for v in val if v]
        parts = re.split(r'[;,\n]+', str(val))
        return [p.strip() for p in parts if p.strip()]

    roles = _extract_list(preferred_roles)
    domains = _extract_list(char.get('domain_interests')) if char else []
    skills = _extract_list(char.get('core_skills')) if char else []
    preferred_stack = _extract_list(char.get('preferred_stack')) if char else []
    headline = (char.get('headline') or '').strip() if char else ''
    projects = _extract_list(char.get('project_highlights')) if char else []

    # preserve the order of user-provided fields and remove duplicates
    candidates = []
    for lst in (roles, domains, [headline] if headline else [], skills, preferred_stack, projects):
        for item in lst:
            if item and item not in candidates:
                candidates.append(item)

    queries = []
    seen_phrases = set()
    stop = False
    for c in candidates:
        if stop:
            break
        c_norm = re.sub(r"\s+", " ", str(c)).strip()
        words = c_norm.split()
        # prefer short variants (first 4 words) to avoid long, noisy queries
        variants = []
        if len(words) > 4:
            variants.append(' '.join(words[:4]))
        variants.append(c_norm)

        for variant in variants:
            if not variant:
                continue
            vkl = variant.lower()
            if vkl in seen_phrases:
                continue
            seen_phrases.add(vkl)

            queries.append(f"{variant} internship {preferred_location or ''}".strip())
            if len(queries) >= max_queries:
                stop = True
                break
            queries.append(f"{variant} intern {preferred_location or ''}".strip())
            if len(queries) >= max_queries:
                stop = True
                break

    # fallback to a minimal generic query only when nothing is provided
    if not queries:
        queries = [f"internship {preferred_location or ''}".strip(), f"intern {preferred_location or ''}".strip()]

    # normalize and dedupe final list
    norm = []
    seen = set()
    for q in queries:
        qn = re.sub(r"\s+", " ", q).strip()
        kl = qn.lower()
        if kl not in seen:
            seen.add(kl)
            norm.append(qn)
        if len(norm) >= max_queries:
            break

    return norm


def search_opportunities(user_id: int) -> list:
    conn = get_db_connection()
    user = conn.execute('SELECT virtual_character, preferred_roles, preferred_location FROM users WHERE id = ?', (user_id,)).fetchone()
    char = json.loads(user['virtual_character']) if user and user['virtual_character'] else {}
    preferred_roles = user['preferred_roles'] if user else ''
    preferred_location = user['preferred_location'] if user else None

    # Prune stale pending opportunities older than 30 days (created_at or date_posted)
    def _prune_stale_opportunities(connection, days: int = 30):
        try:
            from datetime import datetime, timedelta
            cutoff = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')
            connection.execute("UPDATE opportunities SET status = 'expired' WHERE status = 'pending' AND (date(date_posted) IS NOT NULL AND date(date_posted) <= ?)", (cutoff,))
            connection.execute("UPDATE opportunities SET status = 'expired' WHERE status = 'pending' AND date(created_at) <= ?", (cutoff,))
            connection.commit()
        except Exception:
            pass

    _prune_stale_opportunities(conn, days=30)

    def _extract_list(val):
        if not val:
            return []
        if isinstance(val, list):
            return [v for v in val if v]
        parts = re.split(r'[;,\n]+', str(val))
        return [p.strip() for p in parts if p.strip()]

    # Build a list of focused search phrases from onboarding + virtual character
    queries = []
    queries += _extract_list(preferred_roles)
    if char.get('domain_interests'):
        queries += _extract_list(char.get('domain_interests'))
    if char.get('core_skills'):
        queries += _extract_list(char.get('core_skills'))
    if char.get('preferred_stack'):
        queries += _extract_list(char.get('preferred_stack'))
    if char.get('headline'):
        queries += [char.get('headline')]
    if char.get('project_highlights'):
        queries += _extract_list(char.get('project_highlights'))

    # normalize and limit queries
    queries = [q for q in [re.sub(r"\s+", " ", q).strip() for q in queries] if q]
    focused = []
    for q in queries:
        if len(focused) >= 12:
            break
        # prefer explicit internship search phrases
        focused.append(f"{q} internship")
        if len(focused) >= 12:
            break
        focused.append(f"{q} intern")

    # fallback generic if nothing extracted
    if not focused:
        focused = ["internship", "intern"]

    # dedupe focused
    seen_q = []
    # limit external provider calls to avoid hitting TheirStack rate limits
    MAX_EXTERNAL_CALLS = int(os.getenv('THEIRSTACK_MAX_CALLS_PER_SEARCH', '8'))
    calls_made = 0

    for q in focused:
        if q.lower() not in [s.lower() for s in seen_q]:
            seen_q.append(q)
    focused = seen_q

    # Do not blindly delete stored opportunities — we'll prefer DB-first results
    # and upsert provider results so duplicates are avoided.

    # build targeted search queries
    focused = _build_search_queries(char, preferred_roles or '', preferred_location)
    print(f"Phase2 search queries: {focused}")

    # fetch jobs across focused queries with DB-first strategy and upsert results
    jobs_map = {}
    for q in focused:
        q_norm = re.sub(r"\s+", " ", q).strip().lower()

        # 1) search DB first for matching pending opportunities
        likeq = f"%{q_norm}%"
        try:
            cursor = conn.execute(
                "SELECT * FROM opportunities WHERE user_id = ? AND status = 'pending' AND (lower(designation) LIKE ? OR lower(description_summary) LIKE ? OR lower(required_skills) LIKE ?) ORDER BY match_score DESC",
                (user_id, likeq, likeq, likeq)
            )
            for row in cursor.fetchall():
                r = dict(row)
                # ensure required_skills is a list
                try:
                    r['required_skills'] = json.loads(r.get('required_skills') or '[]')
                except Exception:
                    r['required_skills'] = []
                key = r.get('job_id') or f"{r.get('company_name','')}-{r.get('designation','')}"
                if key:
                    jobs_map[key] = r
        except Exception:
            pass

        # If DB already has enough results for this query, skip external calls
        PER_QUERY_DB_THRESHOLD = 8
        db_count = sum(1 for k in jobs_map if q_norm in (k or '').lower() or q_norm in (jobs_map[k].get('designation') or '').lower())
        if db_count >= PER_QUERY_DB_THRESHOLD:
            continue

        # 2) query external providers (TheirStack only) - first page only here
        jobs = []
        if calls_made >= MAX_EXTERNAL_CALLS:
            # we've reached our budget for external API calls this run
            print(f"Skipping external call for '{q}' (max {MAX_EXTERNAL_CALLS} reached)")
            continue

        try:
            res = theirstack_search_jobs(q, preferred_location, limit=10, page=0)
            calls_made += 1
            if isinstance(res, tuple):
                jobs, headers = res
            else:
                jobs = res
        except Exception as e:
            print(f"TheirStack fetch error for '{q}': {e}")

        if not jobs:
            # No provider results for this query; skip
            continue

        if not jobs:
            continue

        for job in jobs:
            computed_score = _compute_match_score(job, char)
            key = job.get('job_id') or f"{job.get('company_name','')}-{job.get('designation','')}"
            if not key:
                continue

            # merge with in-memory map to keep highest score
            if key in jobs_map:
                existing = jobs_map[key]
                combined_score = max(int(existing.get('match_score', 0) or 0), int(computed_score or 0))
                existing.update(job)
                existing['match_score'] = combined_score
                jobs_map[key] = existing
            else:
                entry = job.copy()
                entry['match_score'] = computed_score
                jobs_map[key] = entry

            # upsert into DB (use ON CONFLICT to update existing rows)
            try:
                conn.execute('''
                    INSERT INTO opportunities
                    (user_id, job_id, company_name, designation, location, duration, stipend, apply_url, required_skills, description_summary, source_platform, match_score, date_posted, discovered_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id, job_id, source_platform) DO UPDATE SET
                        company_name=excluded.company_name,
                        designation=excluded.designation,
                        location=excluded.location,
                        duration=excluded.duration,
                        stipend=excluded.stipend,
                        apply_url=excluded.apply_url,
                        required_skills=excluded.required_skills,
                        description_summary=excluded.description_summary,
                        match_score=MAX(opportunities.match_score, excluded.match_score),
                        date_posted=COALESCE(excluded.date_posted, opportunities.date_posted),
                        discovered_at=COALESCE(excluded.discovered_at, opportunities.discovered_at),
                        updated_at=CURRENT_TIMESTAMP,
                        status='pending'
                ''', (
                    user_id,
                    job.get('job_id') or key,
                    job.get('company_name'),
                    job.get('designation'),
                    job.get('location'),
                    job.get('duration'),
                    job.get('stipend'),
                    job.get('apply_url'),
                    json.dumps(job.get('required_skills') or []),
                    job.get('description_summary'),
                    job.get('source_platform') or 'external',
                    int(job.get('match_score') or 50),
                    job.get('date_posted'),
                    job.get('discovered_at')
                ))
                conn.commit()
            except Exception as e:
                # some sqlite versions may not support the ON CONFLICT clause used
                # above; fallback to naive upsert: try update, then insert.
                try:
                    # update first
                    conn.execute('''
                        UPDATE opportunities SET
                            company_name=?, designation=?, location=?, duration=?, stipend=?, apply_url=?, required_skills=?, description_summary=?, match_score=?, date_posted=?, discovered_at=?, updated_at=CURRENT_TIMESTAMP, status='pending'
                        WHERE user_id=? AND job_id=? AND source_platform=?
                    ''', (
                        job.get('company_name'), job.get('designation'), job.get('location'), job.get('duration'), job.get('stipend'), job.get('apply_url'), json.dumps(job.get('required_skills') or []), job.get('description_summary'), int(job.get('match_score') or 50), job.get('date_posted'), job.get('discovered_at'), user_id, job.get('job_id') or key, job.get('source_platform') or 'external'
                    ))
                    if conn.total_changes == 0:
                        conn.execute('''
                            INSERT INTO opportunities (user_id, job_id, company_name, designation, location, duration, stipend, apply_url, required_skills, description_summary, source_platform, match_score, date_posted, discovered_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ''', (
                            user_id,
                            job.get('job_id') or key,
                            job.get('company_name'),
                            job.get('designation'),
                            job.get('location'),
                            job.get('duration'),
                            job.get('stipend'),
                            job.get('apply_url'),
                            json.dumps(job.get('required_skills') or []),
                            job.get('description_summary'),
                            job.get('source_platform') or 'external',
                            int(job.get('match_score') or 50),
                            job.get('date_posted'),
                            job.get('discovered_at')
                        ))
                        conn.commit()
                except Exception as e2:
                    print(f"Insert/Update error: {e2}")

    # If nothing found, try broader fallback queries (bypass short query skips)
    if not jobs_map:
        allowed_limit = MAX_EXTERNAL_CALLS + 3
        if calls_made < allowed_limit:
            fallback_qs = []
            if preferred_location:
                fallback_qs.append(f"internship {preferred_location}".strip())
            # use first two comma-separated roles as fallbacks
            try:
                role_parts = [r.strip() for r in re.split(r'[;,\n]+', preferred_roles) if r.strip()]
            except Exception:
                role_parts = []
            for r in role_parts[:2]:
                fallback_qs.append(f"{r} internship {preferred_location or ''}".strip())
            # generic fallbacks
            fallback_qs.extend(["internship", "internship remote"])

            for fq in fallback_qs:
                if calls_made >= allowed_limit:
                    break
                try:
                    res = theirstack_search_jobs(fq, preferred_location, limit=10, page=0)
                    calls_made += 1
                    if isinstance(res, tuple):
                        jobs, headers = res
                    else:
                        jobs = res
                except Exception as e:
                    print(f"TheirStack fallback fetch error for '{fq}': {e}")
                    continue

                if not jobs:
                    continue

                for job in jobs:
                    computed_score = _compute_match_score(job, char)
                    key = job.get('job_id') or f"{job.get('company_name','')}-{job.get('designation','')}"
                    if not key:
                        continue
                    entry = job.copy()
                    entry['match_score'] = computed_score
                    jobs_map[key] = entry
                    try:
                        _upsert_job(conn, user_id, job, computed_score)
                    except Exception as e:
                        print(f"Fallback upsert error: {e}")

            try:
                conn.commit()
            except Exception:
                pass

        if not jobs_map:
            conn.close()
            return []


    # Insert merged results
    # We already upserted provider results while iterating; ensure DB changes saved
    try:
        conn.commit()
    except Exception:
        pass

    cursor = conn.execute('SELECT * FROM opportunities WHERE user_id = ? AND status = ? ORDER BY match_score DESC', (user_id, 'pending'))
    pending_jobs = []
    for row in cursor.fetchall():
        r = dict(row)
        try:
            r['required_skills'] = json.loads(r.get('required_skills') or '[]')
        except Exception:
            r['required_skills'] = []
        pending_jobs.append(r)
    conn.close()

    return pending_jobs


def _upsert_job(connection, user_id: int, job: Dict[str, Any], computed_score: int):


def load_more_opportunities(user_id: int, page: int = 1, per_page: int = 10):
    """Fetch next pages from TheirStack for all focused queries and upsert results.

    This is intended to run in background (on-demand when the user scrolls).
    """
    conn = get_db_connection()
    user = conn.execute('SELECT virtual_character, preferred_roles, preferred_location FROM users WHERE id = ?', (user_id,)).fetchone()
    char = json.loads(user['virtual_character']) if user and user['virtual_character'] else {}
    preferred_roles = user['preferred_roles'] if user else ''
    preferred_location = user['preferred_location'] if user else None

    focused = _build_search_queries(char, preferred_roles or '', preferred_location)

    for q in focused:
        try:
            res = theirstack_search_jobs(q, preferred_location, limit=per_page, page=page)
            if isinstance(res, tuple):
                jobs, headers = res
            else:
                jobs = res
        except Exception as e:
            print(f"TheirStack load_more fetch error for '{q}' page {page}: {e}")
            continue

        for job in jobs:
            try:
                computed_score = _compute_match_score(job, char)
                _upsert_job(conn, user_id, job, computed_score)
            except Exception as e:
                print(f"Error upserting job in load_more: {e}")

    try:
        conn.commit()
    except Exception:
        pass
    conn.close()

    # If no jobs found at all (DB or external), return empty list
    # If nothing found, try broader fallback queries (bypass short query skips)
    if not jobs_map:
        allowed_limit = MAX_EXTERNAL_CALLS + 3
        if calls_made < allowed_limit:
            fallback_qs = []
            if preferred_location:
                fallback_qs.append(f"internship {preferred_location}".strip())
            # use first two comma-separated roles as fallbacks
            try:
                role_parts = [r.strip() for r in re.split(r'[;,\n]+', preferred_roles) if r.strip()]
            except Exception:
                role_parts = []
            for r in role_parts[:2]:
                fallback_qs.append(f"{r} internship {preferred_location or ''}".strip())
            # generic fallbacks
            fallback_qs.extend(["internship", "internship remote"])

            for fq in fallback_qs:
                if calls_made >= allowed_limit:
                    break
                try:
                    res = theirstack_search_jobs(fq, preferred_location, limit=10, page=0)
                    calls_made += 1
                    if isinstance(res, tuple):
                        jobs, headers = res
                    else:
                        jobs = res
                except Exception as e:
                    print(f"TheirStack fallback fetch error for '{fq}': {e}")
                    continue

                if not jobs:
                    continue

                for job in jobs:
                    computed_score = _compute_match_score(job, char)
                    key = job.get('job_id') or f"{job.get('company_name','')}-{job.get('designation','')}"
                    if not key:
                        continue
                    entry = job.copy()
                    entry['match_score'] = computed_score
                    jobs_map[key] = entry
                    try:
                        _upsert_job(conn, user_id, job, computed_score)
                    except Exception as e:
                        print(f"Fallback upsert error: {e}")

            try:
                conn.commit()
            except Exception:
                pass

        if not jobs_map:
            conn.close()
            return []

    # Insert merged results
    # We already upserted provider results while iterating; ensure DB changes saved
    try:
        conn.commit()
    except Exception:
        pass

    cursor = conn.execute('SELECT * FROM opportunities WHERE user_id = ? AND status = ? ORDER BY match_score DESC', (user_id, 'pending'))
    pending_jobs = []
    for row in cursor.fetchall():
        r = dict(row)
        try:
            r['required_skills'] = json.loads(r.get('required_skills') or '[]')
        except Exception:
            r['required_skills'] = []
        pending_jobs.append(r)
    conn.close()

    return pending_jobs


def process_approval(opp_id: int, decision: str):
    conn = get_db_connection()
    status = 'approved' if decision.lower() in ['y', 'yes'] else ('rejected' if decision.lower() in ['n', 'no'] else 'pending')
    conn.execute('UPDATE opportunities SET status = ? WHERE id = ?', (status, opp_id))
    conn.commit()
    conn.close()
