import db
summary, totals = db.get_business_summary('2026-09-14')
print('Consolidated Totals:')
for k in ['campaigns', 'ventas', 'compras', 'sent', 'opens', 'clicks', 'bounces', 'replies']:
    print(f"  {k}: {totals.get(k):,}")
print('\nBy Line:')
for b in summary:
    print(f"  {b['business']}: Camps={b['campaigns']} | Sent={b['sent']:,} | Opens={b['opens']:,} | Clicks={b['clicks']:,} | Bounces={b['bounces']:,} | Replies={b['replies']:,}")
