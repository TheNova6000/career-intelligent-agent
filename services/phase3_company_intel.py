import json
from database import get_db_connection
from utils.llm_client import generate_json_response

import os
import requests

def get_company_context(company_name: str) -> str:
    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not tavily_key:
        return "No real-time data available. Tavily API key missing."
    
    try:
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": tavily_key,
                "query": f"{company_name} company recent news, future direction, tech stack, and hiring goals",
                "search_depth": "advanced",
                "include_answer": True,
                "max_results": 5
            },
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        context = ""
        if "answer" in data and data["answer"]:
            context += f"Summary: {data['answer']}\n\n"
        
        for idx, result in enumerate(data.get("results", [])):
            context += f"Source {idx+1}: {result.get('title')}\n{result.get('content')}\n\n"
            
        return context if context else "No significant recent web data found."
    except Exception as e:
        print(f"Tavily search error: {e}")
        return f"Error retrieving real-time data: {e}"

def generate_company_report(opp_id: int) -> dict:
    conn = get_db_connection()
    opp = conn.execute('SELECT company_name FROM opportunities WHERE id = ?', (opp_id,)).fetchone()
    company_name = opp['company_name'] if opp else "Unknown"
    
    print(f"Scanning web for {company_name}...")
    web_context = get_company_context(company_name)
    
    prompt = f"""
    You are an expert career strategist and company researcher.
    Analyze the following recent web search data about the company '{company_name}':
    
    WEB DATA:
    {web_context}
    
    Based ONLY on the provided web data (and your general knowledge if the data is sparse), 
    provide a structured JSON report with the following exact keys:
    {{
        "what_company_does": "A concise summary of their core product/service.",
        "future_direction": "Their current trajectory, recent news, or future goals.",
        "why_hiring": "Why they are currently expanding or what roles they seem to need.",
        "tech_they_care_about": ["Array", "of", "relevant", "technologies"],
        "hidden_opportunities": "Any unlisted or implied opportunities based on their trajectory."
    }}
    """
    
    report = generate_json_response(prompt)
    
    conn.execute('''
        INSERT INTO company_reports (opportunity_id, report_data)
        VALUES (?, ?)
    ''', (opp_id, json.dumps(report)))
    conn.commit()
    conn.close()
    
    return report
