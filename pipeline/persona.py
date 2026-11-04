import requests
import json
import re

def should_skip_persona(contact):
    return bool(contact.get('persona'))

def generate_persona(contact, claude_api_key, claude_model, custom_prompt=None):
    is_low_conf = (contact.get('enrichment_confidence') or '').lower() == 'low'

    if custom_prompt and custom_prompt.strip():
        prompt = custom_prompt
        for k, v in contact.items():
            prompt = prompt.replace('{' + str(k) + '}', str(v or ''))
    elif is_low_conf:
        prompt = f"""You are a B2B sales intelligence analyst. Generate a minimal buyer persona for a tech conference attendee with LIMITED data.

RULES:
- Do NOT fabricate any details not in the input.
- Keep everything brief.
- Output ONLY valid JSON. No text before or after.

INPUT:
- Name: {contact.get('name', '')}
- Designation: {contact.get('designation', '')}
- Company: {contact.get('company', '')}
- Industry: {contact.get('industry_vertical', '')}
- Seniority: {contact.get('seniority_level', '')}

JSON:
{{"persona_summary":"1 sentence","goals_and_motivations":["1 bullet"],"pain_points_and_challenges":["1 bullet"],"personalization_hooks":["1 hook"],"confidence":"low","confidence_explanation":"Limited data"}}"""
    else:
        prompt = f"""You are a senior B2B sales intelligence analyst and buyer persona expert with 15+ years creating actionable personas for SaaS/pricing intelligence/competitive benchmarking tools.

Your ONLY sources of truth are the data below. Do NOT invent, assume, or add any facts not present.

INPUT:
- Name: {contact.get('name', '')}
- Designation: {contact.get('designation', '')}
- Company: {contact.get('company', '')}
- Industry: {contact.get('industry_vertical', '')}
- Seniority: {contact.get('seniority_level', '')}
- Company Size: {contact.get('company_size_estimate', '')}
- LinkedIn: {contact.get('linkedin_url') or 'not available'}
- Pain Points: {contact.get('inferred_pain_points') or 'none'}
- Relevance: {contact.get('relevance_score', '')}

Generate ONE buyer persona in strict JSON. Focus on pricing intelligence, competitive benchmarking, data automation.

JSON (no extra fields, no markdown):
{{"persona_summary":"1-2 sentences","goals_and_motivations":["bullet1","bullet2","bullet3"],"pain_points_and_challenges":["bullet1","bullet2","bullet3"],"fears_and_objections":["bullet1","bullet2"],"buying_triggers":["trigger1"],"personalization_hooks":["hook1","hook2","hook3"],"confidence":"high|medium|low","confidence_explanation":"1 sentence"}}"""

    result = {
        'persona': '',
        'context_summary': '',
        'personalization_themes': '',
        'recommended_tone': 'consultative',
        'persona_confidence': 'low'
    }

    try:
        resp = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'Content-Type': 'application/json',
                'x-api-key': claude_api_key,
                'anthropic-version': '2023-06-01'
            },
            json={
                'model': claude_model,
                'max_tokens': 800,
                'messages': [{'role': 'user', 'content': prompt}]
            },
            timeout=30
        )
        text = resp.json().get('content', [{}])[0].get('text', '{}')
        clean = re.sub(r'```json\n?', '', text)
        clean = re.sub(r'```\n?', '', clean).strip()
        # Try direct parse, then extract JSON object
        try:
            obj = json.loads(clean)
        except json.JSONDecodeError:
            match = re.search(r'\{[\s\S]*\}', clean)
            obj = json.loads(match.group()) if match else {}

        result['persona'] = obj.get('persona_summary', '')
        context_parts = obj.get('goals_and_motivations', []) + obj.get('pain_points_and_challenges', [])
        result['context_summary'] = ' | '.join(context_parts)
        result['personalization_themes'] = ' | '.join(obj.get('personalization_hooks', []))
        result['recommended_tone'] = 'peer-to-peer'
        result['persona_confidence'] = (obj.get('confidence') or 'low').lower()

        # Hallucination safeguards
        if is_low_conf:
            result['persona_confidence'] = 'low'
        all_text = result['persona'] + ' ' + result['context_summary']
        if re.search(r'\$[\d,.]+\s*(million|billion|crore|lakh)', all_text, re.I):
            result['persona_confidence'] = 'low'
        if not contact.get('inferred_pain_points') and result['persona_confidence'] == 'high':
            result['persona_confidence'] = 'medium'

    except Exception as e:
        result['persona'] = f'Generation failed: {e}'

    return result
