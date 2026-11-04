import requests
import json
import re

def _parse_json_response(text):
    """Robustly extract JSON from LLM output that may have extra text around it."""
    # Try direct parse first
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown code blocks
    clean = re.sub(r'```json\s*', '', text)
    clean = re.sub(r'```\s*', '', clean).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the text
    match = re.search(r'\{[\s\S]*\}', clean)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Try fixing common issues: single quotes to double quotes
    if match:
        fixed = match.group().replace("'", '"')
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

    # Last resort: try to extract fields manually
    result = {}
    for field in ['email_subject', 'email_body', 'linkedin_message']:
        pattern = rf'"{field}"\s*:\s*"((?:[^"\\]|\\.)*)?"'
        m = re.search(pattern, clean, re.DOTALL)
        if m:
            result[field] = m.group(1).replace('\\"', '"').replace('\\n', '\n')
    if result:
        return result

    raise json.JSONDecodeError(f"Could not parse JSON from response", text, 0)

def should_skip_outreach(contact):
    return bool(contact.get('email_subject'))

DEFAULT_PROMPT = '''You are a senior sales copywriter crafting personalized B2B outreach.

STRICT RULES:
- Sound like a real human. NOT a template. NOT an AI.
- NEVER use: {banned_phrases}
- LinkedIn messages MUST be under 280 characters.
- Keep emails 3-5 sentences. Subject lines must be specific and curiosity-driven.
- End email body with soft CTA: "{soft_cta}"

CONTACT:
Name: {name}
Designation: {designation}
Company: {company}
Tier: {tier} (Score: {tier_score}/100)
Persona: {persona}
Context: {context_summary}
Themes: {personalization_themes}

Output ONLY valid JSON, no markdown:
{{"email_subject":"string","email_body":"3-5 sentences","linkedin_message":"under 280 chars"}}'''

def _format_prompt(template, contact, soft_cta='', banned_phrases=''):
    banned_str = banned_phrases if isinstance(banned_phrases, str) else '\n'.join(banned_phrases)
    replacements = {
        '{name}': contact.get('name', ''),
        '{designation}': contact.get('designation', ''),
        '{company}': contact.get('company', ''),
        '{tier}': contact.get('tier', 'Tier 3'),
        '{tier_score}': str(contact.get('tier_score', 0)),
        '{persona}': contact.get('persona', ''),
        '{context_summary}': contact.get('context_summary', ''),
        '{personalization_themes}': contact.get('personalization_themes', ''),
        '{linkedin_url}': contact.get('linkedin_url', ''),
        '{seniority_level}': contact.get('seniority_level', ''),
        '{industry_vertical}': contact.get('industry_vertical', ''),
        '{company_size_estimate}': contact.get('company_size_estimate', ''),
        '{inferred_pain_points}': contact.get('inferred_pain_points', ''),
        '{relevance_score}': contact.get('relevance_score', ''),
        '{soft_cta}': soft_cta,
        '{banned_phrases}': banned_str,
    }
    result = template
    for k, v in replacements.items():
        result = result.replace(k, str(v))
    return result

def generate_outreach(contact, claude_api_key, claude_model, ollama_url, ollama_model,
                      custom_prompt=None, soft_cta='', banned_phrases=None):
    result = {'email_subject': '', 'email_body': '', 'linkedin_message': ''}
    tier = contact.get('tier', 'Tier 3')
    banned_list = banned_phrases if isinstance(banned_phrases, list) else (banned_phrases or '').split('\n')
    banned_str = ', '.join([b.strip() for b in banned_list if b.strip()])

    prompt_template = custom_prompt if custom_prompt and custom_prompt.strip() else DEFAULT_PROMPT
    prompt = _format_prompt(prompt_template, contact, soft_cta, banned_str)

    try:
        if tier in ('Tier 1', 'Tier 2') and claude_api_key:
            resp = requests.post('https://api.anthropic.com/v1/messages',
                headers={'Content-Type': 'application/json', 'x-api-key': claude_api_key, 'anthropic-version': '2023-06-01'},
                json={'model': claude_model, 'max_tokens': 1500, 'messages': [{'role': 'user', 'content': prompt}]},
                timeout=60)
            text = resp.json().get('content', [{}])[0].get('text', '{}')
        else:
            resp = requests.post(ollama_url, json={
                'model': ollama_model, 'prompt': prompt, 'stream': False,
                'format': 'json', 'options': {'temperature': 0.3, 'num_predict': 1200}
            }, timeout=90)
            text = resp.json().get('response', '{}')

        obj = _parse_json_response(text)
        result['email_subject'] = obj.get('email_subject', '')
        result['email_body'] = obj.get('email_body', '')
        result['linkedin_message'] = obj.get('linkedin_message', '')

        # Truncate LinkedIn to 280
        if result['linkedin_message'] and len(result['linkedin_message']) > 280:
            result['linkedin_message'] = result['linkedin_message'][:277] + '...'

        # Banned phrase check
        all_text = ' '.join(result.values()).lower()
        for phrase in banned_list:
            phrase = phrase.strip().lower()
            if phrase and phrase in all_text:
                result['email_body'] = f'[BANNED: {phrase}] ' + result['email_body']
                break

    except Exception as e:
        result['email_subject'] = 'Generation failed'
        result['email_body'] = f'Error: {e}'

    return result
