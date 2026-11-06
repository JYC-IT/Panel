import sqlite3

conn = sqlite3.connect('data.db')
conn.row_factory = sqlite3.Row

print("--- Revisar weekly_agent_kpis ---")
rows = conn.execute("SELECT * FROM weekly_agent_kpis WHERE name LIKE '%Roy%'").fetchall()
print("Total rows con Roy en weekly_agent_kpis:", len(rows))
for r in rows:
    print(dict(r))

print("\n--- Revisar users ---")
u = conn.execute("SELECT * FROM users WHERE username LIKE '%roy%' OR name LIKE '%roy%'").fetchall()
print("Total en users:", len(u))
for x in u:
    print(dict(x))

conn.close()

