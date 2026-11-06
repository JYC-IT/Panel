import sqlite3

conn = sqlite3.connect('data.db')
c = conn.cursor()

c.execute("PRAGMA table_info(campaigns)")
print("campaigns cols:", c.fetchall())

c.execute("SELECT * FROM campaigns ORDER BY id DESC LIMIT 5")
for r in c.fetchall():
    print(r)

conn.close()
