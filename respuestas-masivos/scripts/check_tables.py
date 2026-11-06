import sqlite3

conn = sqlite3.connect('data.db')
c = conn.cursor()

c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = c.fetchall()
print("Tables in data.db:", tables)

conn.close()
