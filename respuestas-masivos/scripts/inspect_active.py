import os, sys, requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

load_dotenv(os.path.join(BASE_DIR, ".env"))
key = os.getenv('INSTANTLY_API_KEY', '').strip()
from connectors import instantly
camps = instantly.list_campaigns(key)
stats = instantly.campaign_analytics(key)
for c in camps:
    st = c.get('status')
    if st in [0, 1, 2]:
        cid = c.get('id')
        stat = stats.get(cid) or {}
        name = c.get('name')
        sent = stat.get('emails_sent_count', 0)
        print(f"Status {st}: {name} | sent: {sent} | id: {cid}")
