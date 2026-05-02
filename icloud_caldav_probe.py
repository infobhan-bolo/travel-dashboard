#!/usr/bin/env python3
import re
from pathlib import Path

import caldav

CREDS = Path('/Users/bolo/.openclaw/workspace/CREDENTIALS.md')
ICLOUD_URL = 'https://caldav.icloud.com'


def extract_field(block: str, names):
    for name in names:
        m = re.search(rf'-\s*{re.escape(name)}:\s*`([^`]+)`', block, re.I)
        if m:
            return m.group(1)
    return None


def main():
    text = CREDS.read_text()
    m = re.search(r'##\s*icloud\.com(.*?)(?:\n##\s|\Z)', text, re.I | re.S)
    if not m:
        raise RuntimeError('Could not find icloud.com section in CREDENTIALS.md')
    block = m.group(1)
    username = extract_field(block, ['Apple ID', 'Email', 'iCloud Email', 'Username'])
    password = extract_field(block, ['App-Specific Password', 'Password'])
    if not username or not password:
        raise RuntimeError('Missing Apple ID/email or app-specific password in icloud.com section')

    client = caldav.DAVClient(url=ICLOUD_URL, username=username, password=password)
    principal = client.principal()
    calendars = principal.calendars()
    print('calendar_count', len(calendars))
    for cal in calendars:
        try:
            print(cal.name)
        except Exception:
            print(cal)


if __name__ == '__main__':
    main()
