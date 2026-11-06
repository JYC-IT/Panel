import sqlite3

conn = sqlite3.connect('data.db')
c = conn.cursor()

c.execute('''
    UPDATE weekly_team_kpis
    SET outreach_emails_cc = 135842,
        outreach_emails_instantly = 0,
        outreach_sms = 2130,
        total_outreach = 137972,
        opens_count = 44067,
        click_rate = 14.7,
        total_calls = 635,
        kps = 51,
        effectiveness_rate = 8.03,
        notes = 'Hernan no estuvo 2 dias'
    WHERE week_number = 25
''')

# Update campaigns if Forklift is in campaigns
c.execute('''
    UPDATE campaigns
    SET sent_count = 2136, opens_count = 747, clicks_count = 0
    WHERE name LIKE '%Forklift%' AND start_date >= '2026-10-18'
''')

conn.commit()

print("--- WEEK 25 ROW IN weekly_team_kpis ---")
for row in c.execute("SELECT week_number, date_range, outreach_emails_cc, outreach_emails_instantly, outreach_sms, total_outreach, opens_count, click_rate, total_calls, kps, effectiveness_rate, notes FROM weekly_team_kpis WHERE week_number = 25"):
    print(row)

print("\n--- ALL RECENT CAMPAIGNS (Oct 18 onwards) ---")
for row in c.execute("SELECT id, name, source, sent_count, opens_count, clicks_count, start_date FROM campaigns WHERE start_date >= '2026-10-18'"):
    print(row)

print("\n--- LAST 6 WEEKS IN weekly_team_kpis ---")
for row in c.execute("SELECT week_number, date_range, outreach_emails_cc, outreach_emails_instantly, outreach_sms, total_outreach, total_calls, kps, notes FROM weekly_team_kpis ORDER BY week_number DESC LIMIT 6"):
    print(row)

conn.close()
