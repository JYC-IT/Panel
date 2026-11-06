import imaplib, email, os
from dotenv import load_dotenv
load_dotenv()
u = os.getenv('GMAIL_USER')
p = os.getenv('GMAIL_APP_PASSWORD', '').replace(' ', '')
mail = imaplib.IMAP4_SSL('imap.gmail.com')
mail.login(u, p)
mail.select('"[Gmail]/Todos"')

status, data = mail.search(None, '(OR FROM "launchcontrol" SUBJECT "launch control")')
print('Search 1 (launch control):', status, 'Count:', len(data[0].split()) if data[0] else 0)

if not data[0] or len(data[0].split()) == 0:
    status, data = mail.search(None, '(SUBJECT "launch")')
    print('Search 2 (launch):', status, 'Count:', len(data[0].split()) if data[0] else 0)

if data[0]:
    ids = data[0].split()
    for num in ids[-10:]:
        _, msg_data = mail.fetch(num, '(RFC822.HEADER)')
        msg = email.message_from_bytes(msg_data[0][1])
        print('DATE:', msg.get('Date'), '| FROM:', msg.get('From'), '| SUBJ:', msg.get('Subject'))
mail.logout()
