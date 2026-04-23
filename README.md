# Career Intelligence Agent

Career Intelligence Agent is a local-first Flask app for turning messy job hunting into a guided pipeline:

1. understand the candidate through conversational onboarding
2. search and score opportunities
3. let the user approve targets
4. research approved companies
5. generate a personalized cold email draft

The project is built as a sequence of human-approved phases instead of a single chatbot prompt. It keeps data in local SQLite, renders simple server-side pages with Jinja, and uses external AI/search APIs only where they add leverage.

---

## Core Idea

Most job tools do one isolated thing:
- parse a resume
- search jobs
- draft a generic message

This project treats career outreach as a connected system.

Each stage enriches the next one:
- onboarding captures intent, strengths, education, and links
- opportunity discovery uses that profile to search and rank roles
- company research adds real-world context for a specific target
- email generation uses both candidate context and company context

The result is not meant to be fully autonomous. It is meant to be context-rich, opinionated, and human-controlled.

---

## System Philosophy

### 1. Human-in-the-loop by default

The app does not auto-apply or auto-send. The user approves opportunities, reviews research, and decides whether to use the email draft.

### 2. Local-first state

Candidate data, opportunities, company reports, and generated artifacts live in a local SQLite database. This keeps the project easy to run and easy to inspect.

### 3. Phase-based intelligence

Instead of asking one model to do everything at once, the system breaks the workflow into clear phases with narrower prompts and clearer data contracts.

### 4. Pragmatic AI usage

LLMs are used where summarization, synthesis, or rewriting help:
- onboarding profile synthesis
- domain/query expansion
- company research summarization
- cold email drafting and review

Traditional application logic handles:
- routing
- persistence
- scoring
- page flow
- approval state

### 5. Graceful degradation

The app is designed to keep moving when external APIs are rate-limited or unavailable. In practice, some screens may produce partial/fallback output if an AI provider fails.

---

## Current Product Flow

### Phase 1: Onboarding

The user goes through a conversational flow in [`templates/onboarding.html`](./templates/onboarding.html).

The backend route [`/api/onboarding/step`](./routes/api_routes.py) stores data across four steps:
- interests and preferred work mode/location
- skills, projects, experience
- education
- GitHub, LinkedIn, resume, contact details

Then [`/api/onboarding/synthesize`](./routes/api_routes.py) builds a `virtual_character` profile from the collected data.

### Phase 2: Opportunity Discovery

The user lands on [`templates/opportunities.html`](./templates/opportunities.html) and triggers a search.

The main search logic lives in [`services/phase2_opportunities.py`](./services/phase2_opportunities.py), which:
- builds search queries from the candidate profile or a direct query
- optionally expands vague domains with an LLM
- fetches jobs through [`utils/job_aggregator_client.py`](./utils/job_aggregator_client.py)
- computes match scores
- stores/upserts pending opportunities in SQLite

### Phase 3: Company Intelligence

After approving an opportunity, the company screen [`templates/company.html`](./templates/company.html) calls [`/api/company/report/<opp_id>`](./routes/api_routes.py).

The report logic in [`services/phase3_company_intel.py`](./services/phase3_company_intel.py):
- finds the selected company
- gathers real-time context via Tavily
- asks the LLM to produce a structured company report
- stores that report in the database

### Phase 4: Application Strategy

The application strategy page exists in [`templates/application.html`](./templates/application.html). It is part of the intended flow and can be expanded further, but today the strongest implemented behavior is the transition from company research into cold email generation.

### Phase 5: Cold Email Drafting

The cold email screen [`templates/cold_email.html`](./templates/cold_email.html) calls [`/api/email/draft/<opp_id>`](./routes/api_routes.py).

The logic in [`services/phase4_email.py`](./services/phase4_email.py):
- loads the candidate profile
- loads the latest company report
- asks the LLM for an initial cold email draft
- runs a second review prompt to improve it

### Phase 6: Future Scope

The project hints at later workflow automation, but the current repo is centered on:
- onboarding
- opportunity discovery
- company research
- email drafting

---

## Real Architecture

This is the current repo structure that matters most:

```text
job-agent/
├── app.py
├── database.py
├── requirements.txt
├── routes/
│   ├── api_routes.py
│   └── web_routes.py
├── services/
│   ├── phase1_onboarding.py
│   ├── phase2_opportunities.py
│   ├── phase3_company_intel.py
│   └── phase4_email.py
├── templates/
│   ├── application.html
│   ├── base.html
│   ├── cold_email.html
│   ├── company.html
│   ├── dashboard.html
│   ├── landing.html
│   ├── onboarding.html
│   └── opportunities.html
└── utils/
    ├── github_client.py
    ├── job_aggregator_client.py
    ├── llm_client.py
    ├── tavily_client.py
    └── theirstack_client.py
```

### Entry point

[`app.py`](./app.py) creates the Flask app, loads environment variables, initializes the database, and registers the web/API blueprints.

### Web routes

[`routes/web_routes.py`](./routes/web_routes.py) serves the HTML pages:
- `/`
- `/login`
- `/dashboard`
- `/onboarding`
- `/opportunities`
- `/company/<opp_id>`
- `/application/<opp_id>`
- `/cold_email/<opp_id>`

### API routes

[`routes/api_routes.py`](./routes/api_routes.py) handles JSON endpoints for:
- onboarding steps and synthesis
- opportunity search and approval
- company reports
- email drafts
- user switching

Compatibility endpoints are included so the current frontend templates keep working while the backend evolves.

### Service layer

The `services/` directory contains the business logic for each major workflow phase. These modules are where most of the product behavior lives.

### Utility layer

The `utils/` directory wraps external providers and helper integrations such as:
- GitHub profile extraction
- LLM access
- Tavily search
- job source aggregation

---

## Data Model

SQLite is initialized by [`database.py`](./database.py).

The app currently relies on tables for:
- users
- opportunities
- company reports
- GitHub-related data

The onboarding flow updates existing user columns rather than requiring schema changes for each iteration.

Key persisted concepts:
- `users.virtual_character`
- `users.preferred_roles`
- `users.preferred_location`
- `users.preferred_stack`
- `users.degree`
- pending/approved/rejected opportunities
- company intelligence reports

---

## Request Flow

### Onboarding flow

```text
GET /onboarding
  -> onboarding.html
  -> POST /api/onboarding/step (x4)
  -> POST /api/onboarding/synthesize
  -> redirect to /opportunities
```

### Opportunity flow

```text
GET /opportunities
  -> opportunities.html
  -> POST /api/opportunities/search
  -> POST /api/opportunities/approve
  -> redirect to /company/<opp_id>
```

### Research + email flow

```text
GET /company/<opp_id>
  -> GET /api/company/report/<opp_id>
  -> proceed to /application/<opp_id>
  -> proceed to /cold_email/<opp_id>
  -> POST /api/email/draft/<opp_id>
```

---

## AI and Search Dependencies

The app currently integrates with multiple external providers.

### LLM providers

The LLM wrapper in [`utils/llm_client.py`](./utils/llm_client.py) is used by:
- onboarding synthesis
- query/domain expansion
- company intelligence generation
- cold email generation

The current setup attempts provider fallback, but behavior depends on provider quotas and SDK compatibility.

### Search / aggregation providers

The app uses:
- Tavily for company context and real-time research
- JSearch / Remotive / related sources through `job_aggregator_client.py`

### Important operational note

If OpenRouter is rate-limited or another provider fails, parts of the workflow may still return a `200` response with fallback or incomplete data. This is a product limitation to keep in mind during demos and testing.

---

## Setup

### Requirements

- Python 3.10+
- pip
- a virtual environment
- API keys for the services you actually want to use

### Install

```bash
git clone <your-repo-url>
cd job-agent
python -m venv venv
```

On Windows:

```powershell
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

On macOS/Linux:

```bash
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then edit `.env` with your real keys.

### Run

```bash
python app.py
```

App URL:

```text
http://127.0.0.1:5001
```

The database is initialized automatically on startup.

---

## Environment Variables

See [`.env.example`](./.env.example) for the latest template.

Typical variables:

```env
GEMINI_API_KEY=your_gemini_api_key
GROQ_API_KEY=your_groq_api_key
OPEN_ROUTER=your_openrouter_api_key
TAVILY_API_KEY=your_tavily_api_key
GITHUB_TOKEN=your_github_token
THEIRSTACK_API_KEY=your_theirstack_api_key
JSEARCH_API_KEY=your_jsearch_api_key
ADZUNA_APP_ID=your_adzuna_app_id
ADZUNA_APP_KEY=your_adzuna_app_key
FLASK_APP=app.py
FLASK_ENV=development
FLASK_SECRET_KEY=replace_with_a_strong_secret_key
```

---

## Multi-user and Session Behavior

The app now uses session-based user selection for the active browser session.

Important behavior:
- visiting `/onboarding` without an active session user creates a fresh user profile
- `/login` creates a new test/profile user
- `/dashboard` lets you inspect and switch between saved users
- API endpoints use `session["user_id"]` instead of trusting a posted `user_id`

This was added to stop different onboarding runs from mixing data into a single profile.

---

## What Is Working Now

Based on the current codebase and recent testing, the following path works:

- onboarding step progression
- virtual character synthesis
- opportunity search
- opportunity approval
- company report generation
- transition into application and cold email pages

The app also includes compatibility endpoints so older frontend fetch calls still resolve correctly.

---

## Known Limitations

### 1. External AI limits affect output quality

If OpenRouter is rate-limited or another provider fails, downstream phases may:
- fall back to another provider
- return weaker output
- show blank or partial content if the fallback does not match the expected schema

### 2. Cold email generation is only as strong as the model response

The cold email path currently assumes structured JSON from the model. If the provider fails or returns malformed output, the UI may not show a complete draft.

### 3. Company reports are regenerated on demand

The current company report path can re-run the intelligence step when revisiting a company page instead of aggressively caching and reusing reports.

### 4. The application strategy phase is lighter than the other phases

The repo includes an application page in the flow, but the deepest implemented logic today is around company research and email generation.

### 5. This is still a local prototype

The app is not production-hardened. It is optimized for:
- experimentation
- demos
- local iteration

Not for:
- secure multi-tenant deployment
- background workers
- production email delivery

---

## Why This Project Is Interesting

This project is more than a job board wrapper. Its interesting design idea is the pipeline:

- candidate context is collected once
- approvals happen at the right moments
- research is tied to a chosen opportunity
- generated outreach is grounded in both self-context and company-context

That makes it a useful prototype for:
- career tooling
- agentic workflow design
- multi-phase AI systems
- local-first product experiments

---

## GitHub Push Notes

Before pushing publicly:

1. keep `.env` out of Git
2. rotate any keys that were ever accidentally exposed
3. verify `.env.example` contains only placeholders
4. make sure local SQLite databases and logs are not committed

The repo has already been cleaned to help with that:
- generated DB files removed
- debug artifacts removed
- `.gitignore` tightened
- `.env.example` sanitized

---

## Suggested Roadmap

- strengthen cold email fallback behavior when providers return malformed data
- cache and reuse company reports more aggressively
- improve the application strategy phase into a first-class report
- add better error messaging in the UI for rate-limit failures
- add export/share support for candidate dossiers
- add tests for the route contracts and JSON shapes
- split provider integrations into cleaner adapters with explicit response schemas

---

## License

Add the license you want before pushing publicly. If you want permissive open source, MIT is a simple default.
