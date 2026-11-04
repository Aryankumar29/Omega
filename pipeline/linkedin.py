import requests
import re

def should_skip_linkedin(contact):
    return bool(contact.get('linkedin_url'))

def score_candidate(result, contact):
    url = (result.get('url') or '').lower()
    if 'linkedin.com/in/' not in url:
        return -1
    for bad in ['/company/', '/jobs/', '/pub/dir', '/school/', '/search/results/', '/dir/']:
        if bad in url:
            return -1
    score = 0
    title = (result.get('title') or '').lower()
    desc = (result.get('description') or result.get('snippet') or '').lower()
    name_lower = contact.get('name', '').lower()

    if name_lower in title:
        score += 50
    elif name_lower.replace(' ', '-') in url:
        score += 40

    company = (contact.get('company') or '').lower()
    if company and (company in title or company in desc):
        score += 30

    designation = (contact.get('designation') or '').lower()
    if designation and (designation in title or designation in desc):
        score += 25

    return score

def find_linkedin(contact, brave_api_key):
    result = {'linkedin_url': '', 'linkedin_status': 'not_found'}

    try:
        query = f"{contact.get('name', '')} {contact.get('company', '')} linkedin"
        resp = requests.get(
            'https://api.search.brave.com/res/v1/web/search',
            params={'q': query, 'count': 5},
            headers={
                'Accept': 'application/json',
                'Accept-Encoding': 'gzip',
                'X-Subscription-Token': brave_api_key
            },
            timeout=15
        )
        data = resp.json()
        best_url = None
        best_score = -1

        for r in data.get('web', {}).get('results', []):
            s = score_candidate(r, contact)
            if s > best_score:
                best_score = s
                url = r.get('url', '').split('?')[0].split('&')[0]
                best_url = url

        if best_url and best_score >= 40:
            result['linkedin_url'] = best_url
            result['linkedin_status'] = 'found'
    except Exception as e:
        result['linkedin_status'] = 'error'

    return result
