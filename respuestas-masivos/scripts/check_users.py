import os
import sys
import requests
from dotenv import load_dotenv

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(root_dir, ".env"))
api_key = os.getenv("CLOSE_CRM_API_KEY")

r = requests.get("https://api.close.com/api/v1/user/", auth=(api_key, ""))
users = r.json().get("data", [])

print("--- ALL USERS IN CLOSE CRM ---")
target_names = [
    "Hernan Bonilla",
    "Juan Abuchaibe",
    "Juan Arango",
    "Juan Cordoba",
    "Julian Prado",
    "Mariana Polanco",
    "Roy Jones",
    "Sebastian Jordan"
]

selected_ids = []
for u in users:
    name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
    email = u.get("email", "")
    uid = u.get("id")
    print(f"Name: {name:20} | Email: {email:30} | ID: {uid}")
    for t in target_names:
        if t.lower() in name.lower():
            selected_ids.append((name, uid))

print("\n--- SELECTED 8 USERS ---")
for s_name, s_id in selected_ids:
    print(f"{s_name} -> {s_id}")
