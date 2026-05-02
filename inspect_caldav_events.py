#!/usr/bin/env python3
import re
from pathlib import Path
from datetime import datetime, date
import caldav

CREDS = Path('/Users/bolo/.openclaw/workspace/CREDENTIALS.md')
ICLOUD_URL = 'https://caldav.icloud.com'
TARGETS = [
    ('Ishir', '2026-06-09', '2026-06-20'),
    ('Ishir', '2026-08-25', '2026-09-02'),
    ('Ishir', '2026-09-08', '2026-09-15'),
    ('Ishir', '2026-09-22', '2026-09-28'),
]


def extract_field(block: str, names):
    for name in names:
        m = re.search(rf'-\s*{re.escape(name)}:\s*`([^`]+)`', block, re.I)
        if m:
            return m.group(1)
    return None

text = CREDS.read_text()
m = re.search(r'##\s*icloud\.com(.*?)(?:\n##\s|\Z)', text, re.I | re.S)
block = m.group(1)
username = extract_field(block, ['Apple ID', 'Email', 'iCloud Email', 'Username'])
password = extract_field(block, ['App-Specific Password', 'Password'])
client = caldav.DAVClient(url=ICLOUD_URL, username=username, password=password)
principal = client.principal()
cals = {cal.name: cal for cal in principal.calendars()}

for cal_name, start_s, end_s in TARGETS:
    start = datetime.fromisoformat(start_s)
    end = datetime.fromisoformat(end_s)
    print('\n===', cal_name, start_s, end_s, '===')
    results = cals[cal_name].search(start=start, end=end, event=True, expand=False)
    for ev in results:
        try:
            comp = ev.icalendar_instance.walk('VEVENT')[0]
        except Exception:
            continue
        summary = str(comp.get('summary', ''))
        dtstart = comp.decoded('dtstart')
        dtend = comp.decoded('dtend') if comp.get('dtend') else None
        print({
            'summary': summary,
            'dtstart': repr(dtstart),
            'dtend': repr(dtend),
            'dtstart_type': type(dtstart).__name__,
            'dtend_type': type(dtend).__name__ if dtend is not None else None,
        })
