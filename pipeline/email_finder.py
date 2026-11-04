import requests
import re
import time

def should_skip_email(contact):
    return bool(contact.get('email'))

def get_snov_token(client_id, client_secret):
    resp = requests.post('https://api.snov.io/v1/oauth/access_token', json={
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret
    }, timeout=10)
    return resp.json().get('access_token')

def snov_find_email(token, first_name, last_name, domain):
    resp = requests.post('https://api.snov.io/v2/email-finder/start',
        headers={'Authorization': f'Bearer {token}'},
        json={'rows': [{'first_name': first_name, 'last_name': last_name, 'domain': domain}]},
        timeout=15)
    task_hash = resp.json().get('meta', {}).get('task_hash')
    if not task_hash:
        return None

    for _ in range(5):
        time.sleep(2)
        result = requests.get(f'https://api.snov.io/v2/email-finder/result/{task_hash}',
            headers={'Authorization': f'Bearer {token}'}, timeout=10)
        data = result.json()
        if data.get('status') == 'completed' and data.get('data', {}).get('rows'):
            row = data['data']['rows'][0]
            if row.get('emails') and row['emails'][0].get('email'):
                return {
                    'email': row['emails'][0]['email'],
                    'status': row['emails'][0].get('smtp_status', 'found')
                }
            return None
    return None

def find_domain(company, brave_api_key):
    resp = requests.get('https://api.search.brave.com/res/v1/web/search',
        params={'q': f'{company} official website', 'count': 3},
        headers={
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip',
            'X-Subscription-Token': brave_api_key
        }, timeout=10)
    results = resp.json().get('web', {}).get('results', [])
    if results:
        match = re.match(r'https?://(?:www\.)?([^/]+)', results[0].get('url', ''))
        if match:
            return match.group(1)
    return None

def find_email(contact, brave_api_key, snov_client_id=None, snov_client_secret=None):
    result = {'email': '', 'email_status': 'not_found', 'email_confidence': 0, 'email_source': ''}

    name = contact.get('name', '')
    clean_name = re.sub(r"^(Hon'ble\s+Minister\s+Shri\s+|Hon'ble\s+|Shri\s+|Dr\.?\s+|Mr\.?\s+|Mrs\.?\s+)", "", name, flags=re.I).strip()
    parts = clean_name.split()
    first_name = parts[0] if parts else ''
    last_name = ' '.join(parts[1:]) if len(parts) > 1 else ''
    tier = contact.get('tier', '')
    company = contact.get('company', '')

    # Layer 1: Snov.io (Tier 1 only)
    if tier == 'Tier 1' and snov_client_id and snov_client_secret:
        try:
            token = get_snov_token(snov_client_id, snov_client_secret)
            if token:
                domain = find_domain(company, brave_api_key)
                if domain:
                    found = snov_find_email(token, first_name, last_name, domain)
                    if found:
                        result['email'] = found['email']
                        result['email_status'] = 'snov_verified' if found['status'] == 'valid' else 'snov_found'
                        result['email_confidence'] = 90 if found['status'] == 'valid' else 60
                        result['email_source'] = 'snov.io'
                        return result
            time.sleep(1.1)
        except Exception:
            pass

    # Layer 2: Brave email search (T1 fallback + T2)
    if not result['email'] and tier in ('Tier 1', 'Tier 2') and brave_api_key:
        try:
            query = f'{name} {company} email contact'
            resp = requests.get('https://api.search.brave.com/res/v1/web/search',
                params={'q': query, 'count': 10},
                headers={
                    'Accept': 'application/json',
                    'Accept-Encoding': 'gzip',
                    'X-Subscription-Token': brave_api_key
                }, timeout=10)
            email_regex = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
            generic = {'example.com', 'noreply', 'support@', 'info@', 'contact@', 'admin@', 'help@', 'sales@', 'hr@'}
            for r in resp.json().get('web', {}).get('results', []):
                text = f"{r.get('title', '')} {r.get('description', r.get('snippet', ''))} {r.get('url', '')}"
                matches = email_regex.findall(text)
                for m in matches:
                    if not any(g in m.lower() for g in generic):
                        result['email'] = m
                        result['email_status'] = 'brave_found'
                        result['email_confidence'] = 50
                        result['email_source'] = 'brave_search'
                        return result
            time.sleep(1.1)
        except Exception:
            pass

    # Layer 3: Domain construction (all tiers)
    if not result['email'] and brave_api_key:
        try:
            domain = find_domain(company, brave_api_key)
            if domain:
                first = re.sub(r'[^a-z]', '', first_name.lower())
                if first:
                    result['email'] = f'{first}@{domain}'
                    result['email_status'] = 'domain_constructed'
                    result['email_confidence'] = 30
                    result['email_source'] = 'constructed'
            else:
                result['email_status'] = 'no_domain_found'
            time.sleep(1.1)
        except Exception:
            result['email_status'] = 'all_failed'

    return result
