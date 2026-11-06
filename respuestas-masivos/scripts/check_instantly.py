import sqlite3
conn = sqlite3.connect('data.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, name, sent_count, opens_count, clicks_count, bounces_count, start_date, created_at FROM campaigns WHERE source = 'instantly' ORDER BY sent_count DESC LIMIT 20").fetchall()
print(f"Total Instantly in DB: {len(rows)}")
for r in rows:
    print(dict(r))
