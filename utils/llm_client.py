import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

open_router_key = os.getenv("OPEN_ROUTER")
OPENROUTER_API_KEY = open_router_key.strip() if open_router_key else None

def call_openrouter(prompt: str, json_mode: bool = False) -> str:
    response = requests.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": "http://localhost:5000",
            "X-Title": "Career Intelligence Agent"
        },
        json={
            "model": "openrouter/free", 
            "messages": [{"role": "user", "content": prompt}]
        },
        timeout=15
    )
    response.raise_for_status()
    res_json = response.json()
    return res_json['choices'][0]['message']['content']

def generate_json_response(prompt: str) -> dict:
    if OPENROUTER_API_KEY:
        try:
            # Instruct the model to strictly return JSON in case the model ignores response_format
            prompt_with_json = prompt + "\n\nCRITICAL: Return ONLY valid JSON. Return an object."
            content = call_openrouter(prompt_with_json, json_mode=True)
            
            # Robust JSON extraction
            import re
            content = content.strip()
            # Find the first { and last }
            start = content.find('{')
            end = content.rfind('}')
            if start != -1 and end != -1:
                content = content[start:end+1]
            
            return json.loads(content)
        except Exception as e:
            print(f"Error calling OpenRouter API: {e}")
            try:
                print(f"Content was: {content}")
            except:
                pass
            print("Falling back to Gemini...")

    try:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY", "").strip())
        model = genai.GenerativeModel('gemini-1.5-pro-latest')
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return {}

def generate_text_response(prompt: str) -> str:
    if OPENROUTER_API_KEY:
        try:
            return call_openrouter(prompt, json_mode=False)
        except Exception as e:
            print(f"Error calling OpenRouter API: {e}")
            print("Falling back to Gemini...")

    try:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY", "").strip())
        model = genai.GenerativeModel('gemini-1.5-pro-latest')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return ""
