import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'career_agent.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            phone TEXT,
            college TEXT,
            degree TEXT,
            grad_year TEXT,
            gpa TEXT,
            preferred_location TEXT,
            preferred_roles TEXT,
            preferred_stack TEXT,
            virtual_character JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS resumes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_path TEXT,
            parsed_data JSON,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        
        CREATE TABLE IF NOT EXISTS github_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            extracted_data JSON,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        
        CREATE TABLE IF NOT EXISTS linkedin_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            profile_url TEXT,
            extracted_data JSON,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        
        CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            job_id TEXT,
            company_name TEXT,
            designation TEXT,
            location TEXT,
            duration TEXT,
            stipend TEXT,
            apply_url TEXT,
            required_skills TEXT,
            description_summary TEXT,
            source_platform TEXT,
            match_score INTEGER,
            status TEXT DEFAULT 'pending', -- pending, approved, rejected
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            opportunity_id INTEGER,
            resume_used TEXT,
            cover_letter TEXT,
            status TEXT DEFAULT 'preparing', -- preparing, applied, interviewing, rejected
            applied_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (opportunity_id) REFERENCES opportunities (id)
        );
        
        CREATE TABLE IF NOT EXISTS company_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id INTEGER,
            report_data JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (opportunity_id) REFERENCES opportunities (id)
        );
        
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            opportunity_id INTEGER,
            recipient_email TEXT,
            subject TEXT,
            body TEXT,
            status TEXT DEFAULT 'draft',
            sent_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (opportunity_id) REFERENCES opportunities (id)
        );
        
        CREATE TABLE IF NOT EXISTS feedback_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER,
            feedback_analysis JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (application_id) REFERENCES applications (id)
        );
    ''')
    conn.commit()
    # Apply lightweight migrations for opportunities table to add fields
    # if they don't already exist. This keeps existing DB files compatible.
    try:
        c.execute("PRAGMA table_info(opportunities)")
        cols = {row[1] for row in c.fetchall()}  # row[1] is column name

        # Add common job metadata columns if missing
        if 'date_posted' not in cols:
            c.execute("ALTER TABLE opportunities ADD COLUMN date_posted TEXT")
        if 'discovered_at' not in cols:
            c.execute("ALTER TABLE opportunities ADD COLUMN discovered_at TEXT")
        if 'expires_at' not in cols:
            c.execute("ALTER TABLE opportunities ADD COLUMN expires_at TEXT")
        if 'updated_at' not in cols:
            c.execute("ALTER TABLE opportunities ADD COLUMN updated_at TIMESTAMP")

        # Ensure a unique index to avoid duplicate job records per user/source
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_opportunities_unique ON opportunities (user_id, job_id, source_platform)")
        conn.commit()
    except Exception:
        # If migration fails, keep going — app will still function, but without
        # the new columns. We avoid crashing user's DB on schema changes.
        pass

    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")
