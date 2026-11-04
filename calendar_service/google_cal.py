import json
import datetime
import requests

SCOPES = ['https://www.googleapis.com/auth/calendar']
GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
CALENDAR_API = 'https://www.googleapis.com/calendar/v3'

def get_auth_url(client_id, redirect_uri):
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': ' '.join(SCOPES),
        'access_type': 'offline',
        'prompt': 'consent'
    }
    qs = '&'.join(f'{k}={requests.utils.quote(str(v))}' for k, v in params.items())
    return f'{GOOGLE_AUTH_URL}?{qs}'

def handle_callback(code, client_id, client_secret, redirect_uri):
    resp = requests.post(GOOGLE_TOKEN_URL, data={
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code'
    }, timeout=15)
    data = resp.json()
    if 'error' in data:
        raise Exception(f"Google OAuth error: {data.get('error_description', data['error'])}")
    return {
        'access_token': data['access_token'],
        'refresh_token': data.get('refresh_token', ''),
        'expires_in': data.get('expires_in', 3600)
    }

def refresh_token(client_id, client_secret, refresh_tok):
    resp = requests.post(GOOGLE_TOKEN_URL, data={
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_tok,
        'grant_type': 'refresh_token'
    }, timeout=15)
    data = resp.json()
    return data.get('access_token', '')

def _get_headers(access_token):
    return {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

def get_free_slots(access_token, date_str, timezone='Asia/Kolkata'):
    """Get available 30-min slots for a given date between 9 AM and 6 PM."""
    dt = datetime.datetime.strptime(date_str, '%Y-%m-%d')
    time_min = dt.replace(hour=9, minute=0).isoformat() + '+05:30'
    time_max = dt.replace(hour=18, minute=0).isoformat() + '+05:30'

    resp = requests.post(f'{CALENDAR_API}/freeBusy',
        headers=_get_headers(access_token),
        json={
            'timeMin': time_min,
            'timeMax': time_max,
            'timeZone': timezone,
            'items': [{'id': 'primary'}]
        }, timeout=15)

    data = resp.json()
    busy_periods = data.get('calendars', {}).get('primary', {}).get('busy', [])

    # Generate all 30-min slots
    all_slots = []
    current = dt.replace(hour=9, minute=0)
    end = dt.replace(hour=18, minute=0)
    while current < end:
        all_slots.append(current.strftime('%H:%M'))
        current += datetime.timedelta(minutes=30)

    # Remove busy slots
    busy_times = set()
    for period in busy_periods:
        start = datetime.datetime.fromisoformat(period['start'].replace('Z', '+00:00'))
        end_b = datetime.datetime.fromisoformat(period['end'].replace('Z', '+00:00'))
        # Mark all 30-min blocks that overlap
        check = dt.replace(hour=9, minute=0)
        while check < dt.replace(hour=18, minute=0):
            slot_end = check + datetime.timedelta(minutes=30)
            # Simple overlap check using hour/minute comparison
            if check.strftime('%H:%M') not in busy_times:
                pass  # Will check properly below
            check += datetime.timedelta(minutes=30)

    # Simpler approach: just return all slots minus busy ones
    free_slots = []
    for slot_str in all_slots:
        h, m = map(int, slot_str.split(':'))
        slot_start = dt.replace(hour=h, minute=m)
        slot_end = slot_start + datetime.timedelta(minutes=30)
        is_busy = False
        for period in busy_periods:
            try:
                bs = datetime.datetime.fromisoformat(period['start'].replace('Z', '+00:00')).replace(tzinfo=None)
                be = datetime.datetime.fromisoformat(period['end'].replace('Z', '+00:00')).replace(tzinfo=None)
                if slot_start < be and slot_end > bs:
                    is_busy = True
                    break
            except Exception:
                pass
        if not is_busy:
            free_slots.append(slot_str)

    return free_slots

def create_meeting(access_token, title, datetime_str, duration_minutes, attendee_email, timezone='Asia/Kolkata', add_meet=True):
    """Create a Google Calendar event with optional Meet link."""
    start_dt = datetime.datetime.fromisoformat(datetime_str)
    end_dt = start_dt + datetime.timedelta(minutes=duration_minutes)

    event = {
        'summary': title,
        'start': {
            'dateTime': start_dt.isoformat(),
            'timeZone': timezone
        },
        'end': {
            'dateTime': end_dt.isoformat(),
            'timeZone': timezone
        },
        'attendees': [{'email': attendee_email}],
        'reminders': {
            'useDefault': False,
            'overrides': [{'method': 'popup', 'minutes': 15}]
        }
    }

    if add_meet:
        event['conferenceData'] = {
            'createRequest': {
                'requestId': f'omega-{datetime.datetime.now().timestamp()}',
                'conferenceSolutionKey': {'type': 'hangoutsMeet'}
            }
        }

    params = {'sendUpdates': 'all'}
    if add_meet:
        params['conferenceDataVersion'] = 1

    resp = requests.post(
        f'{CALENDAR_API}/calendars/primary/events',
        headers=_get_headers(access_token),
        params=params,
        json=event,
        timeout=15
    )

    data = resp.json()
    if 'error' in data:
        raise Exception(f"Calendar error: {data['error'].get('message', str(data['error']))}")

    meet_link = ''
    if data.get('conferenceData', {}).get('entryPoints'):
        for ep in data['conferenceData']['entryPoints']:
            if ep.get('entryPointType') == 'video':
                meet_link = ep.get('uri', '')
                break

    return {
        'event_id': data.get('id', ''),
        'meet_link': meet_link,
        'event_url': data.get('htmlLink', '')
    }
