#!/bin/bash
echo "Setting up Career Intelligence Agent..."
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python database.py
echo "Setup complete! Run 'python app.py' to start the server."
