import sqlite3

conn = sqlite3.connect('data.db')
c = conn.cursor()

# Exact numbers from Constant Contact screenshot:
# 1. Hospitals (ID 2379)
c.execute("UPDATE campaigns SET sent_count=49646, opens_count=15006, clicks_count=1182 WHERE id=2379")

# 2. Cartagena (ID 2376)
c.execute("UPDATE campaigns SET sent_count=1123, opens_count=370, clicks_count=21 WHERE id=2376")

# 3. CAT 980 (ID 4307)
c.execute("UPDATE campaigns SET sent_count=50343, opens_count=21297, clicks_count=0 WHERE id=4307")

# 4. Krauss 13 (ID 2378)
c.execute("UPDATE campaigns SET sent_count=32594, opens_count=6647, clicks_count=5259 WHERE id=2378")

# 5. Forklift (ID 2377)
c.execute("UPDATE campaigns SET sent_count=2136, opens_count=747, clicks_count=0 WHERE id=2377")

conn.commit()

print("Updated campaigns for Week 25:")
for row in c.execute("SELECT id, name, sent_count, opens_count, clicks_count FROM campaigns WHERE id IN (2379, 2376, 4307, 2378, 2377)"):
    print(row)

# Sum check
c.execute("SELECT SUM(sent_count), SUM(opens_count), SUM(clicks_count) FROM campaigns WHERE id IN (2379, 2376, 4307, 2378, 2377)")
print("Total CC campaigns sum:", c.fetchone())

conn.close()
