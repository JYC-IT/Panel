import sqlite3

conn = sqlite3.connect('data.db')
conn.row_factory = sqlite3.Row

print("="*90)
print("  ÚLTIMAS 20 CAMPAÑAS ENVIADAS EN CONSTANT CONTACT (sent_count > 0)")
print("="*90)
cc = conn.execute("""
    SELECT id, name, start_date, sent_count, opens_count, clicks_count, reply_to_email
    FROM campaigns
    WHERE source = 'constantcontact' AND sent_count > 0
    ORDER BY start_date DESC, id DESC
    LIMIT 20
""").fetchall()

for idx, r in enumerate(cc, 1):
    rate = round(100.0 * r['clicks_count'] / r['sent_count'], 2) if r['sent_count'] else 0
    name = r['name'][:42]
    dt = r['start_date'] or 'S/F'
    print(f"{idx:2d}. [{dt}] {name:<42} | Env: {r['sent_count']:>7,d} | Op: {r['opens_count']:>6,d} | Clics: {r['clicks_count']:>5,d} ({rate:.2f}%)")

print("\n" + "="*90)
print("  ÚLTIMAS 20 CAMPAÑAS ENVIADAS EN INSTANTLY (sent_count > 0)")
print("="*90)
inst = conn.execute("""
    SELECT c.id, c.name, c.start_date, c.sent_count, c.opens_count, c.clicks_count,
           (SELECT count(*) FROM replies rep WHERE rep.campaign_id = c.id AND rep.is_auto = 0) as replies
    FROM campaigns c
    WHERE c.source = 'instantly' AND c.sent_count > 0
    ORDER BY c.start_date DESC, c.id DESC
    LIMIT 20
""").fetchall()

for idx, r in enumerate(inst, 1):
    rate = round(100.0 * r['replies'] / r['sent_count'], 2) if r['sent_count'] else 0
    name = r['name'][:42]
    dt = r['start_date'] or 'S/F'
    print(f"{idx:2d}. [{dt}] {name:<42} | Env: {r['sent_count']:>7,d} | Op: {r['opens_count']:>6,d} | Resp: {r['replies']:>4,d} ({rate:.2f}%)")

conn.close()

