# Career Intelligence Agent (CIA)

> *An autonomous, end-to-end career pipeline that replaces fragmented job hunting with a single intelligent assembly line — from who you are, to the perfect cold email.*

---

## What is this?

Most "AI job tools" are glorified resume parsers or chatbots that spit out generic cover letters. The Career Intelligence Agent is something different.

It's a **6-phase autonomous pipeline** that:
1. Learns who you are through a conversational onboarding flow and synthesizes a **Virtual Character** — a JSON persona that captures your tone, writing style, strengths, and differentiators.
2. Scrapes live job listings, scores them by relevance, and presents them through a **Tinder-style approval UI** — you swipe yes/no before anything moves forward.
3. **Deep-researches every approved company** using live web search — blog posts, engineering articles, recent hires, GitHub repos — to understand where they're headed, not just what they advertise.
4. Runs a **skill-gap analysis** by comparing your Virtual Character against company intelligence, then gives you concrete action items (mini-projects to build, technologies to study).
5. Generates a **hyper-personalised cold email** using a two-pass LLM system — first draft using your persona + company context, second pass self-reviewing against a strict quality checklist.
6. Lets you review, edit, and send — entirely your call, every time.

No templates. No filler. Every output is specific to you and to that company.

---

## System Philosophy

### The Assembly Line Approach

Traditional job hunting is a context-switching nightmare: LinkedIn tab, company website tab, email client, resume editor, repeat. Information lives in silos. Every email starts from scratch.

The CIA treats job searching as a **manufacturing pipeline**. Each phase enriches the context passed to the next. By the time you reach email generation, the system holds:

- Your complete professional identity (Virtual Character)
- Verified, approved job targets
- Deep intelligence on each company's current trajectory
- A gap analysis telling you exactly what to highlight or fix
- A self-reviewed email draft tailored to that company's specific moment

The result is outreach that reads like it was written by someone who already works there.

### The Virtual Character

The central innovation is the **Virtual Character** — a structured JSON persona built from your conversational onboarding, LinkedIn tone analysis, and GitHub project fingerprint. It captures:

- Your writing tone (formal / technical / warm / conversational)
- Core skills and domain interests
- Project highlights with contextual framing
- Unique differentiators — things that make you *you*, not every other candidate
- Academic snapshot and contact information

Every downstream phase references this character. The company research is filtered through it. The skill gap is measured against it. The email is *written in its voice*.

### Human-in-the-Loop by Design

The agent is powerful but never autonomous about things that matter. There are three intentional gates where it stops and waits for you:

1. **Job approval** — you review and approve each listing before research begins
2. **Pre-email review** — you see the company dossier and action brief before committing to outreach
3. **Email send** — the agent drafts; you review, edit, and trigger

Nothing goes out without your explicit approval.

---

## Architecture

```
career-intelligent-agent/
│
├── app.py                  # Flask app factory — registers blueprints, inits DB
├── database.py             # SQLite schema init — users, jobs, companies, emails
├── requirements.txt        # Python dependencies
├── setup.sh                # One-command setup script (macOS/Linux)
│
├── routes/
│   ├── web_routes.py       # Page routes — renders HTML templates
│   └── api_routes.py       # REST API endpoints — called by frontend JS
│
├── services/               # Business logic layer
│   ├── llm_service.py      # OpenRouter / Gemini API wrapper — all LLM calls
│   ├── tavily_service.py   # Tavily REST API wrapper — live web search
│   ├── scraper_service.py  # Job listing aggregation engine
│   └── email_service.py    # Two-pass email generation + mailto builder
│
├── templates/              # Jinja2 HTML templates (Tailwind CSS via CDN)
│   ├── index.html          # Landing / onboarding chat
│   ├── discovery.html      # Tinder-style job approval UI
│   ├── company.html        # Company intelligence dashboard
│   ├── strategy.html       # Skill gap + action brief
│   └── email.html          # Email review and send UI
│
└── utils/
    ├── character.py        # Virtual Character synthesis from raw profile data
    └── scorer.py           # Job relevance scoring against Virtual Character
```

---

## The 6 Phases

### Phase 1 — User Profile Intelligence

**Goal:** Build the Virtual Character.

The user enters an LLM-driven conversational onboarding flow — no boring forms. The agent asks about career goals, education, projects, skills, and preferred work style. It also ingests LinkedIn and GitHub URLs, extracting tone, writing style, project descriptions, and technology fingerprints.

All of this is synthesised into a `virtual_character` JSON object and stored in SQLite. This object is the soul of everything that follows.

**What gets captured:**
- Target roles, domains, preferred locations
- Education — degree, institution, grades, scores
- Top projects — problem, stack, outcome
- Writing tone extracted from LinkedIn posts
- Technologies and commit patterns from GitHub
- Contact details, resume data, personal links

---

### Phase 2 — Opportunity Discovery

**Goal:** Find and approve the right jobs.

A scraping engine aggregates internship and job listings from configured sources. Each listing is scored 0–100 for relevance against the Virtual Character's skills, domain interests, and location preferences. Only listings above a threshold are surfaced.

The user sees them one at a time through a **Tinder-style card UI** (built with Tailwind CSS): company name, designation, location, stipend, required skills, match score. Respond Y / N / maybe. Only approved listings advance.

---

### Phase 3 — Company Intelligence Engine

**Goal:** Understand each company's current trajectory.

For every approved company, the agent performs live research via the **Tavily Search API** — company blog posts (last 6 months), engineering articles, recent GitHub activity, job description signals, founder social media, and product announcements.

The result is a structured **Company Intelligence Document** covering:
- Current product focus and recent feature launches
- Technologies in use and technologies they're moving toward
- Open source repos and what they reveal about technical direction
- Repeated skills in recent job descriptions (hiring signals)
- Culture and values signals from public content

---

### Phase 4 — Application Strategy & Skill Gap Analysis

**Goal:** Tell you exactly what to do before writing a single word.

The LLM compares the Virtual Character against the Company Intelligence Document to identify:

- **Skill overlaps** — what you already have that they care about
- **Skill gaps** — what they're looking for that you haven't demonstrated
- **Suggested mini-projects** — 1–2 small, buildable things using their actual stack that would signal genuine interest
- **Learning recommendations** — specific docs, papers, or courses to skim before outreach
- **Talking points** — 2–3 things to reference in the email that show you understand the company's direction

A **Candidate Action Brief** is shown to the user before Phase 5. You can act on it first — build the mini-project, do the reading — or proceed immediately. Your choice.

---

### Phase 5 — Personalised Cold Email Engine

**Goal:** Write an email that sounds like you wrote it, for this company, right now.

This is the most technically interesting phase. It uses a **two-pass LLM system**:

**Pass 1 — Draft generation.** The LLM receives the full Virtual Character, Company Intelligence Document, the Candidate Action Brief, and a strict writing prompt. Rules include: opening must reference one specific recent thing the company shipped; paragraph 2 must connect the candidate's most relevant project directly to the company's tech direction; offer something concrete in paragraph 3; no filler phrases ("passionate", "quick learner", "team player"); 180–220 words maximum; tone must match `virtual_character.tone`.

**Pass 2 — Self-review.** The draft is fed back to the LLM with a checklist: Does the opening reference something specific? Does the project connection feel genuine? Is it under 220 words? Does it avoid all filler? Does it end with a clear, low-pressure ask? If any check fails, that section is rewritten.

The user gets the final draft in an **editable review UI**. They can modify freely. When satisfied, a `mailto:` link fires it into their local mail client — no email credentials stored anywhere, no automated sending.

---

### Phase 6 — Application Tracking *(Future Scope)*

- Automated application form filling
- Follow-up scheduling and nudge system
- Response rate analytics
- Feedback loop: which email patterns convert to replies

---

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Backend | Python 3.10+, Flask | Blueprints for web + API routes |
| Database | SQLite3 | Zero-config, local, no server needed |
| Frontend | HTML5, Vanilla JS | No framework overhead |
| Styling | Tailwind CSS (CDN) | No build step required |
| LLM | OpenRouter API | Free tier available — see below |
| LLM (alt) | Google Gemini SDK | Gemini Flash is free-tier |
| Live Search | Tavily Search API | Free tier: 1,000 searches/month |

---

## Free APIs — No Cost to Get Started

You can run this entire project on **$0/month** using free tiers:

| Service | Free Tier | Get Key |
|---|---|---|
| **OpenRouter** | Free models available (`mistralai/mistral-7b-instruct:free`, `google/gemma-2-9b-it:free`, and more) | [openrouter.ai/keys](https://openrouter.ai/keys) |
| **Google Gemini** | Gemini 1.5 Flash — 15 RPM, 1M TPD free | [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| **Tavily Search** | 1,000 API calls/month free | [tavily.com](https://tavily.com) |
| **GitHub API** | 60 unauthenticated requests/hour (5,000 with token) | [github.com/settings/tokens](https://github.com/settings/tokens) |
| **SQLite** | Completely free, built into Python | No signup |

The `.env.example` file uses OpenRouter + Tavily as defaults. Swap in Gemini at any time by changing one line in `services/llm_service.py`.

---

## Setup & Installation

### Prerequisites

- Python 3.10+
- Git
- API keys for OpenRouter (or Gemini) + Tavily

### macOS / Linux

```bash
# 1. Clone
git clone https://github.com/TheNova6000/career-intelligent-agent.git
cd career-intelligent-agent

# 2. Virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Open .env and fill in OPEN_ROUTER and TAVILY_API_KEY

# 5. Init database and run
python database.py
python app.py
```

### Windows

```bash
# 1. Clone
git clone https://github.com/TheNova6000/career-intelligent-agent.git
cd career-intelligent-agent

# 2. Virtual environment
python -m venv venv
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
copy .env.example .env
# Open .env in Notepad or VS Code and fill in your keys

# 5. Init database and run
python database.py
python app.py
```

App runs at **http://127.0.0.1:5001**

### Environment Variables

```env
# .env

OPEN_ROUTER=your_openrouter_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here

# Optional — only needed if using Gemini instead of OpenRouter
GEMINI_API_KEY=your_gemini_api_key_here
```

---

## Note on Python Compatibility

If you're running Python 3.14+ (early alpha builds), you may hit C-compilation errors from packages like `playwright` or the native `google-generativeai` SDK.

This project is specifically built to avoid those issues — it uses **REST APIs everywhere** (Tavily HTTP API instead of the native SDK, `requests` for all LLM calls). There are no packages that require native C-extension compilation. It runs cleanly on Python 3.10 through 3.13 and on current 3.14 alphas.

---

## How It's Different From Other Tools

| | CIA | Generic AI Resume Tools | Job Boards |
|---|---|---|---|
| Learns your actual tone | ✅ Virtual Character synthesis | ❌ Generic templates | ❌ |
| Live company research | ✅ Tavily real-time search | ❌ Static data | ❌ |
| Skill gap analysis | ✅ Per-company, actionable | ❌ | ❌ |
| Two-pass email review | ✅ Draft + self-critique | ❌ | ❌ |
| Human-in-the-loop gates | ✅ 3 mandatory approval points | ❌ | ❌ |
| Zero external data storage | ✅ Local SQLite only | ❌ Usually cloud | ❌ |
| Free to run | ✅ All free-tier APIs | ❌ Most are paid | ✅ |

---

## Roadmap

- [x] Phase 1 — Conversational onboarding + Virtual Character synthesis
- [x] Phase 2 — Job discovery + approval UI
- [x] Phase 3 — Company intelligence via Tavily
- [x] Phase 4 — Skill gap analysis + Candidate Action Brief
- [x] Phase 5 — Two-pass personalised email generation
- [ ] Phase 6 — Application form auto-fill
- [ ] Follow-up scheduler and nudge system
- [ ] Analytics dashboard — reply rate, open rate by strategy
- [ ] LinkedIn profile data extraction (authenticated)
- [ ] Hackathon and research opportunity discovery
- [ ] Multi-user support (currently single-user local setup)

---

## Contributing

Pull requests are welcome. For significant changes, open an issue first to discuss the direction.

If you're extending the scraping engine (Phase 2), note that LinkedIn blocks most scrapers — the current implementation uses a mockable engine by design. For production scraping, Apify's LinkedIn actor or Proxycurl are the practical options.

---

## License

MIT License — fork it, build on it, ship it.

---

*Built by [TheNova6000](https://github.com/TheNova6000)*