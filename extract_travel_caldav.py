#!/usr/bin/env python3
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import caldav

BASE = Path('/Users/bolo/.openclaw/workspace/travel-dashboard')
OUT = BASE / 'data.json'
CREDS = Path('/Users/bolo/.openclaw/workspace/CREDENTIALS.md')
ICLOUD_URL = 'https://caldav.icloud.com'
MONTHS_AHEAD = 6

CALENDARS = {
    'Ishir': {'home': 'BOS', 'key': 'ishir'},
    'Duyen': {'home': 'BOS', 'key': 'duyen'},
    'Family': {'home': 'BOS', 'key': 'family'},
}

AIRPORT_TIMEZONES = {
    'AMS': 'Europe/Amsterdam',
    'ATL': 'America/New_York',
    'BLR': 'Asia/Kolkata',
    'BOM': 'Asia/Kolkata',
    'BOS': 'America/New_York',
    'DFW': 'America/Chicago',
    'GOX': 'Asia/Kolkata',
    'ICN': 'Asia/Seoul',
    'JNB': 'Africa/Johannesburg',
    'KRK': 'Europe/Warsaw',
    'LHR': 'Europe/London',
    'MSP': 'America/Chicago',
    'ORD': 'America/Chicago',
    'SFO': 'America/Los_Angeles',
    'SJU': 'America/Puerto_Rico',
}


def extract_field(block: str, names):
    for name in names:
        m = re.search(rf'-\s*{re.escape(name)}:\s*`([^`]+)`', block, re.I)
        if m:
            return m.group(1)
    return None


def get_icloud_credentials():
    text = CREDS.read_text()
    m = re.search(r'##\s*icloud\.com(.*?)(?:\n##\s|\Z)', text, re.I | re.S)
    if not m:
        raise RuntimeError('Could not find icloud.com section in CREDENTIALS.md')
    block = m.group(1)
    username = extract_field(block, ['Apple ID', 'Email', 'iCloud Email', 'Username'])
    password = extract_field(block, ['App-Specific Password', 'Password'])
    if not username or not password:
        raise RuntimeError('Missing Apple ID/email or app-specific password in icloud.com section')
    return username, password


def month_ranges(start_month: date, months: int):
    y, m = start_month.year, start_month.month
    for _ in range(months):
        first = date(y, m, 1)
        if m == 12:
            nxt = date(y + 1, 1, 1)
        else:
            nxt = date(y, m + 1, 1)
        yield first, nxt
        y, m = nxt.year, nxt.month


def next_six_months():
    today = date.today()
    start_month = date(today.year, today.month, 1)
    return list(month_ranges(start_month, MONTHS_AHEAD))


def normalize_text(s: str) -> str:
    return str(s).replace('\u200b', '').replace('\xa0', ' ').replace('\u202f', ' ').strip()


def airport_codes(summary: str):
    summary = normalize_text(summary)
    m = re.search(r'✈\s*([A-Z]{3})\s*→\s*([A-Z]{3})', summary)
    if m:
        return m.group(1), m.group(2)
    return None, None


def destination_label(summary: str, dest_code: str):
    text = normalize_text(summary)
    if '→' in text:
        return text.split('→', 1)[1].strip()
    return dest_code


def detail_record(kind: str, text: str, **extra):
    rec = {'kind': kind, 'text': text}
    rec.update(extra)
    return rec


def merge_ranges(ranges):
    if not ranges:
        return []
    ranges = sorted(ranges)
    merged = [list(ranges[0])]
    for start, end in ranges[1:]:
        last_start, last_end = merged[-1]
        if start <= (last_end + timedelta(days=1)):
            if end > last_end:
                merged[-1][1] = end
        else:
            merged.append([start, end])
    return [(a, b) for a, b in merged]


def to_local_naive(dt):
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return datetime(dt.year, dt.month, dt.day)
    if dt.tzinfo is not None:
        return dt.astimezone().replace(tzinfo=None)
    return dt


def to_event_datetime(dt):
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return datetime(dt.year, dt.month, dt.day)
    return dt


def to_local_tz(dt, airport_code):
    if not isinstance(dt, datetime):
        return None
    tz_name = AIRPORT_TIMEZONES.get(airport_code)
    if not tz_name:
        return dt
    zone = ZoneInfo(tz_name)
    if dt.tzinfo is not None:
        return dt.astimezone(zone)
    return dt.replace(tzinfo=zone)


def format_flight_time(dt, airport_code):
    local_dt = to_local_tz(dt, airport_code)
    if local_dt is None:
        return None
    tz_label = local_dt.tzname() or AIRPORT_TIMEZONES.get(airport_code, '')
    return f"{local_dt.strftime('%-I:%M %p')} {tz_label}" if tz_label else local_dt.strftime('%-I:%M %p')


def day_offset_for_display(reference_day, dt, airport_code):
    local_dt = to_local_tz(dt, airport_code)
    if local_dt is None:
        return 0
    return (local_dt.date() - reference_day).days


def fetch_events():
    username, password = get_icloud_credentials()
    client = caldav.DAVClient(url=ICLOUD_URL, username=username, password=password)
    principal = client.principal()
    calendars = {cal.name: cal for cal in principal.calendars()}

    months = next_six_months()
    window_start = datetime.combine(months[0][0], datetime.min.time())
    window_end = datetime.combine(months[-1][1], datetime.min.time())

    events = {name: [] for name in CALENDARS}
    for cal_name in CALENDARS:
        cal = calendars.get(cal_name)
        if cal is None:
            raise RuntimeError(f'Calendar not found via iCloud CalDAV: {cal_name}')
        results = cal.search(start=window_start, end=window_end, event=True, expand=False)
        for ev in results:
            try:
                data = ev.icalendar_instance
                component = data.walk('VEVENT')[0]
            except Exception:
                continue
            summary = normalize_text(component.get('summary', ''))
            dtstart = component.decoded('dtstart')
            dtend = component.decoded('dtend') if component.get('dtend') else dtstart
            is_all_day = isinstance(dtstart, date) and not isinstance(dtstart, datetime)
            start = to_event_datetime(dtstart)
            end = to_event_datetime(dtend)
            events[cal_name].append({
                'summary': summary,
                'start': start,
                'end': end,
                'is_all_day': is_all_day,
            })
    return events, months


def event_day_range(event):
    start_day = event['start'].date()
    end_day = event['end'].date()
    if event.get('is_all_day', False) and end_day > start_day:
        end_day -= timedelta(days=1)
    return start_day, end_day


def flight_day_range(start_dt, end_dt, origin, dest):
    start_local = to_local_tz(start_dt, origin)
    end_local = to_local_tz(end_dt, dest)
    start_day = start_local.date() if start_local else start_dt.date()
    end_day = end_local.date() if end_local else end_dt.date()
    return start_day, end_day


def away_info(events, home='BOS'):
    flights = []
    trip_events = []
    for event in events:
        summary = normalize_text(event['summary'])
        if summary.startswith('Duyen:') or summary.startswith('Ishir:'):
            continue
        origin, dest = airport_codes(summary)
        if origin and dest:
            start_day, end_day = flight_day_range(event['start'], event['end'], origin, dest)
            flights.append({
                'origin': origin,
                'dest': dest,
                'destination_label': destination_label(summary, dest),
                'summary': summary,
                'start': event['start'],
                'end': event['end'],
                'start_day': start_day,
                'end_day': end_day,
            })
            continue
        lower = summary.lower()
        if 'trip' in lower or 'travel' in lower or 'vacation' in lower:
            start_day, end_day = event_day_range(event)
            trip_events.append({
                'summary': summary,
                'start_day': start_day,
                'end_day': end_day,
                'is_all_day': event.get('is_all_day', False),
            })

    flights.sort(key=lambda x: x['start'])
    flight_blocks = []
    away_start = None
    current_flights = []
    for flight in flights:
        if flight['origin'] == home and away_start is None:
            away_start = flight['start_day']
            current_flights = [flight]
            if flight['dest'] == home:
                flight_blocks.append({'start': away_start, 'end': flight['end_day'], 'flights': current_flights[:]})
                away_start = None
                current_flights = []
            continue
        if away_start is not None:
            current_flights.append(flight)
            if flight['dest'] == home:
                flight_blocks.append({'start': away_start, 'end': flight['end_day'], 'flights': current_flights[:]})
                away_start = None
                current_flights = []

    ranges = []
    details = {}

    def add_detail(day, kind, text, **extra):
        key = day.isoformat()
        details.setdefault(key, [])
        record = detail_record(kind, text, **extra)
        if record not in details[key]:
            details[key].append(record)

    for block in flight_blocks:
        ranges.append((block['start'], block['end']))
        cur = block['start']
        while cur <= block['end']:
            matching_flights = [f for f in block['flights'] if f['start_day'] <= cur <= f['end_day']]
            if matching_flights:
                for flight in matching_flights:
                    add_detail(
                        cur,
                        'flight',
                        flight['summary'],
                        departure_time=format_flight_time(flight['start'], flight['origin']),
                        arrival_time=format_flight_time(flight['end'], flight['dest']),
                        departure_day_offset=day_offset_for_display(cur, flight['start'], flight['origin']),
                        arrival_day_offset=day_offset_for_display(cur, flight['end'], flight['dest']),
                        origin=flight['origin'],
                        dest=flight['dest'],
                    )
            else:
                previous = [f for f in block['flights'] if f['start_day'] <= cur]
                if previous:
                    add_detail(cur, 'stay', previous[-1]['destination_label'])
            cur += timedelta(days=1)

    extra_trip_blocks = []
    for trip in trip_events:
        overlaps = any(not (trip['end_day'] < block['start'] or trip['start_day'] > block['end']) for block in flight_blocks)
        if trip.get('is_all_day', False) and not overlaps:
            extra_trip_blocks.append((trip['start_day'], trip['end_day']))
        cur = trip['start_day']
        while cur <= trip['end_day']:
            add_detail(cur, 'trip', trip['summary'])
            cur += timedelta(days=1)

    return {
        'ranges': merge_ranges(ranges + extra_trip_blocks),
        'details': details,
    }


def build_data():
    events, months = fetch_events()

    info = {}
    for cal_name, meta in CALENDARS.items():
        info[meta['key']] = away_info(events[cal_name], home=meta['home'])

    payload_months = []
    for start_d, end_d in months:
        days = {}
        day_details = {}
        cur = start_d
        while cur < end_d:
            active = [key for key in ['ishir', 'duyen', 'family'] if any(a <= cur <= b for a, b in info[key]['ranges'])]
            if len(active) == 1:
                days[str(cur.day)] = active[0]
            elif len(active) > 1:
                days[str(cur.day)] = 'both'

            items = []
            seen = set()
            for key, label in [('ishir', 'Ishir'), ('duyen', 'Duyen'), ('family', 'Family')]:
                for detail in info[key]['details'].get(cur.isoformat(), []):
                    text = detail['text']
                    if detail['kind'] == 'stay':
                        text = f'Staying in {text}'
                    record = {
                        'person': label,
                        'kind': detail['kind'],
                        'text': text,
                    }
                    for extra_key in ('departure_time', 'arrival_time', 'departure_day_offset', 'arrival_day_offset', 'origin', 'dest'):
                        if detail.get(extra_key) is not None:
                            record[extra_key] = detail.get(extra_key)
                    marker = (record['person'], record['kind'], record['text'])
                    if marker in seen:
                        continue
                    seen.add(marker)
                    items.append(record)
            if items:
                day_details[str(cur.day)] = items
            cur += timedelta(days=1)
        payload_months.append({'year': start_d.year, 'month': start_d.month, 'days': days, 'details': day_details})

    payload = {
        'generated_at': datetime.now().isoformat(),
        'months': payload_months,
        'legend': {
            'none': 'Home',
            'ishir': 'Ishir away',
            'duyen': 'Duyen away',
            'family': 'Family away',
            'both': 'Multiple away',
        },
        'ranges': {
            who: [[a.isoformat(), b.isoformat()] for a, b in vals['ranges']]
            for who, vals in info.items()
        },
    }
    OUT.write_text(json.dumps(payload, indent=2))
    print(OUT)


if __name__ == '__main__':
    build_data()
