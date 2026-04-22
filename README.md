# Career Intelligence Agent (CIA)

The **Career Intelligence Agent (CIA)** is a full-stack, autonomous career management system designed to reduce the fragmented, manual effort students and professionals face when searching for internships, jobs, hackathons, and research opportunities.

This is NOT a simple chatbot, a job board, or a resume parser. It is an end-to-end "assembly line" that unifies profiling, discovery, deep-research, skill-gap analysis, and highly personalized cold outreach into a single intelligent pipeline.

---

## 🧠 System Philosophy & Architecture

The core philosophy of the system is the **Assembly Line Approach**. Traditional job searching requires jumping between disconnected platforms (LinkedIn, Wellfound, company blogs, email clients). The Career Intelligence Agent unifies these into 6 cohesive phases:

1. **User Profile Intelligence (Onboarding)**
   - **How it works**: Instead of filling out boring forms, the user engages in a conversational onboarding flow with an LLM. 
   - **Implementation**: The LLM extracts data, tone, and preferences to synthesize a rich "Virtual Character" stored in a SQLite database. This ensures all future actions *sound* exactly like the user.

2. **Opportunity Discovery**
   - **How it works**: The system acts as an approval gate for aggregated opportunities (internships, jobs, hackathons).
   - **Implementation**: A mockable scraping engine aggregates roles, presenting them via a Tinder-like approval UI built with Tailwind CSS.

3. **Company Intelligence Engine (Deep Research)**
   - **How it works**: Before applying, the system deeply researches the company to understand their current trajectory.
   - **Implementation**: The agent uses the **Tavily REST API** to scour the live web for recent news, blog posts, and hiring goals, feeding that context into the LLM to populate a structured intelligence dashboard.

4. **Application Strategy & Skill Gap Analysis**
   - **How it works**: Compares the Virtual Character against the Company Intelligence to find overlaps and gaps.
   - **Implementation**: The LLM outputs actionable strategies (e.g., "Build a 1-week Kubernetes project to cover this gap") before moving to outreach.

5. **Personalized Cold Outreach (Email Engine)**
   - **How it works**: Drafts a highly specific cold email that avoids generic filler and leverages deep context.
   - **Implementation**: A two-pass LLM system. *Pass 1* drafts the email using the Virtual Character tone and Tavily web data. *Pass 2* self-reviews against a strict checklist. The user gets a UI to review, edit, and trigger the email directly into their local mail client (`mailto:`).

6. **Application Engine & Tracking** *(Future Scope)*
   - Automated form filling and feedback loop integration.

---

## 🚀 Tech Stack

- **Backend**: Python, Flask, SQLite3
- **Frontend**: HTML5, Vanilla JavaScript, Tailwind CSS (via CDN)
- **AI/LLM**: OpenRouter API (`openrouter/free` fallback), Google Gemini SDK
- **Live Search**: Tavily Search API

---

## 🛠️ Setup & Installation

The setup is slightly different depending on your operating system.

### Prerequisites (Both OS)
- Python 3.10+ installed
- Git installed
- API Keys: OpenRouter API key (or Groq/Gemini), Tavily API Key

### 🍎 For macOS / Linux

1. **Clone the repository**
   ```bash
   git clone https://github.com/TheNova6000/career-intelligent-agent.git
   cd career-intelligent-agent
   ```

2. **Create and activate a virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Setup Environment Variables**
   ```bash
   cp .env.example .env
   ```
   *Open `.env` and fill in your `OPEN_ROUTER` and `TAVILY_API_KEY` values.*

5. **Initialize the Database & Run the App**
   ```bash
   python database.py
   python app.py
   ```
   The app will run at `http://127.0.0.1:5001`.

---

### 🪟 For Windows

1. **Clone the repository**
   ```cmd
   git clone https://github.com/TheNova6000/career-intelligent-agent.git
   cd career-intelligent-agent
   ```

2. **Create and activate a virtual environment**
   ```cmd
   python -m venv venv
   venv\Scripts\activate
   ```

3. **Install dependencies**
   ```cmd
   pip install -r requirements.txt
   ```

4. **Setup Environment Variables**
   ```cmd
   copy .env.example .env
   ```
   *Open `.env` in Notepad or VS Code and fill in your `OPEN_ROUTER` and `TAVILY_API_KEY` values.*

5. **Initialize the Database & Run the App**
   ```cmd
   python database.py
   python app.py
   ```
   The app will run at `http://127.0.0.1:5001`.

---

## 💡 Note on Native Extensions (Python 3.14+)
If you are running very new alpha versions of Python (like Python 3.14), you may encounter C-compilation errors with packages like `playwright` or `google.generativeai`. 
- **The Workaround:** This codebase is specifically optimized to avoid native C-extension compilation errors by utilizing REST APIs (Tavily HTTP API instead of the native SDK, and standard `requests` for OpenRouter).

## 📄 License
MIT License. Feel free to fork and build upon this!
