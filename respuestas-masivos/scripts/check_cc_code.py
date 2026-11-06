import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from connectors import google_workspace
from datetime import datetime

users = ["support@jycequipment.com", "jp@jycmedical.com", "julianp@jyccorporation.com"]

for u in users:
    print(f"\n--- Revisando buzón: {u} ---")
    try:
        s = google_workspace._get_gmail_service(u)
        res = s.users().messages().list(
            userId="me",
            q="Constant Contact OR verification OR security code OR código",
            maxResults=5
        ).execute()
        msgs = res.get("messages", [])
        if not msgs:
            print("  (Sin mensajes recientes coincidentes)")
            continue
        for m in msgs:
            detail = s.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"]
            ).execute()
            headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
            print(f"  Fecha: {headers.get('Date')}")
            print(f"  De: {headers.get('From')}")
            print(f"  Asunto: {headers.get('Subject')}")
            print(f"  Snippet: {detail.get('snippet')[:140]}")
            print("-" * 50)
    except Exception as e:
        print(f"  Error al consultar {u}: {e}")
