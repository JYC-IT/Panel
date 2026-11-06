import os, json, sqlite3, requests
from dotenv import load_dotenv
load_dotenv()

conn = sqlite3.connect('data.db')
conn.row_factory = sqlite3.Row

print("=== 1. CONSTANT CONTACT CAMPAIGNS IN DB (OCT 19 - OCT 23) ===")
rows = conn.execute("""
    SELECT id, name, sent_count, opens_count, clicks_count, bounces_count, start_date, created_at
    FROM campaigns 
    WHERE source = 'constantcontact' 
      AND start_date >= '2026-10-19' AND start_date <= '2026-10-23'
    ORDER BY start_date DESC
""").fetchall()

print(f"Total campaigns in Week 25: {len(rows)}")
tot_sent = sum(r['sent_count'] for r in rows)
tot_opens = sum(r['opens_count'] for r in rows)
tot_clicks = sum(r['clicks_count'] for r in rows)
tot_bounces = sum(r['bounces_count'] for r in rows)
print(f"Totals: Sent={tot_sent:,}, Opens={tot_opens:,}, Clicks={tot_clicks:,}, Bounces={tot_bounces:,}")
for r in rows:
    print(f"  [{r['start_date']}] {r['name']} | Sent: {r['sent_count']:,} | Opens: {r['opens_count']:,} | Clicks: {r['clicks_count']:,}")

print("\n=== ALL RECENT CONSTANT CONTACT (SINCE OCT 12) ===")
recent = conn.execute("""
    SELECT name, sent_count, opens_count, clicks_count, bounces_count, start_date 
    FROM campaigns 
    WHERE source = 'constantcontact' AND start_date >= '2026-10-12'
    ORDER BY start_date DESC
""").fetchall()
for r in recent:
    print(f"  [{r['start_date']}] {r['name']} | Sent: {r['sent_count']:,}")

print("\n=== 2. INSTANTLY CAMPAIGNS CREATED/ACTIVE IN OCT 2026 ===")
inst_rows = conn.execute("""
    SELECT name, sent_count, opens_count, clicks_count, bounces_count, start_date
    FROM campaigns 
    WHERE source = 'instantly' AND (start_date >= '2026-10-01' OR name LIKE '%2026-10%')
    ORDER BY start_date DESC
""").fetchall()
print(f"Instantly campaigns in Oct 2026: {len(inst_rows)}")
for r in inst_rows:
    print(f"  [{r['start_date']}] {r['name']} | Sent: {r['sent_count']:,} | Opens: {r['opens_count']:,}")

print("\n=== 3. REPLIES RECEIVED IN WEEK 25 (OCT 19 - OCT 23) ===")
replies = conn.execute("""
    SELECT count(*), c.source 
    FROM replies r
    JOIN campaigns c ON c.id = r.campaign_id
    WHERE r.received_at >= '2026-10-19' AND r.received_at <= '2026-10-24'
    GROUP BY c.source
""").fetchall()
for r in replies:
    print(f"  Source: {r[1]} -> {r[0]} replies")
