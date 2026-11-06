import sqlite3

conn = sqlite3.connect('data.db')
c = conn.cursor()

ranges = [
    (20, 'Sep 14 - 18', 'Festivo Lunes'),
    (21, 'Sep 21 - 25', 'Viaje Hernan y Sebastian'),
    (22, 'Sep 28 - Oct 2', 'Viaje Sebastian'),
    (23, 'Oct 5 - 9', 'Sebastian no estuvo 2 dias'),
    (24, 'Oct 12 - 16', 'Rodrigo no estuvo 2 dias'),
    (25, 'Oct 19 - 23', 'Hernan no estuvo 2 dias')
]

for w, dr, note in ranges:
    c.execute("UPDATE weekly_team_kpis SET date_range=?, notes=? WHERE week_number=?", (dr, note, w))

conn.commit()

for row in c.execute("SELECT week_number, date_range, notes FROM weekly_team_kpis ORDER BY week_number ASC"):
    print(row)

conn.close()
