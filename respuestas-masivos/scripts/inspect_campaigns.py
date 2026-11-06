import db

with db.get_conn() as conn:
    rows = conn.execute("SELECT id, name, match_subject, reply_to_email, start_date, sent_count, opens_count, clicks_count FROM campaigns ORDER BY id DESC").fetchall()
    print(f"Total campaigns: {len(rows)}")
    for r in rows[:40]:
        print(f"[{r['id']}] {r['name']} | Subj: {r['match_subject']} | ReplyTo: {r['reply_to_email']}")
