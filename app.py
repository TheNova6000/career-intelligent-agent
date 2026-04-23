from flask import Flask
from database import init_db
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "job-agent-dev-secret-key")

# Initialize database on startup
init_db()

# Import routes after app initialization to avoid circular imports
from routes import web_routes, api_routes
app.register_blueprint(web_routes.bp)
app.register_blueprint(api_routes.api_bp)

if __name__ == '__main__':
    app.run(debug=True, port=5001)
