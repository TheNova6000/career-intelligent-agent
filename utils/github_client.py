import requests
import os

def get_github_profile(username: str) -> dict:
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Authorization": f"token {token}"} if token else {}
    
    try:
        user_resp = requests.get(f"https://api.github.com/users/{username}", headers=headers)
        repos_resp = requests.get(f"https://api.github.com/users/{username}/repos?sort=updated&per_page=5", headers=headers)
        
        user_data = user_resp.json() if user_resp.status_code == 200 else {}
        repos_data = repos_resp.json() if repos_resp.status_code == 200 else []
        
        pinned_repos = [
            {
                "name": r.get("name"),
                "description": r.get("description"),
                "languages": r.get("language"),
                "stars": r.get("stargazers_count"),
                "topics": r.get("topics", [])
            } for r in repos_data
        ]
        
        return {
            "bio": user_data.get("bio"),
            "public_repos": user_data.get("public_repos"),
            "followers": user_data.get("followers"),
            "pinned_repos": pinned_repos
        }
    except Exception as e:
        print(f"GitHub API Error: {e}")
        return {}
