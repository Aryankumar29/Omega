import requests
import json

def should_skip_enrichment(contact):
    return bool(contact.get('seniority_level') and contact.get('industry_vertical'))

def enrich_contact(contact, ollama_url, ollama_model, custom_prompt=None):
    name = contact.get('name', '')
    designation = contact.get('designation', '')
    company = contact.get('company', '')

    if custom_prompt and custom_prompt.strip():
        prompt = custom_prompt.replace('{name}', name).replace('{designation}', designation).replace('{company}', company)
    else:
        prompt = None

    if not prompt:
        prompt = f"""You are a B2B sales intelligence analyst. Given data about a tech conference attendee in India, infer the requested fields.

STRICT RULES:
- Only infer what the data supports. If unsure, use "Unknown".
- Seniority: Founder/Co-founder/CEO/CTO/CMO/COO/CFO/Chairman = C-Suite. VP/SVP/EVP/Head of = VP. Director/GM = Director. Manager/Lead/Senior = Manager. Minister/Secretary = C-Suite. Else = IC. Ambiguous = Unknown.
- Relevance to pricing intelligence, competitive benchmarking, data automation: HIGH: e-commerce, retail, D2C, SaaS, marketplace, analytics, supply chain, fintech, logistics. MEDIUM: general tech, cloud, AI/ML, consulting, enterprise software, telecom. LOW: government, NGO, media, education (non-edtech), VC/PE.
- Company size: use knowledge of well-known companies. Founder at unknown = Startup. Unknown = Unknown.
- Confidence: HIGH if well-known company + clear title. MEDIUM if one unclear. LOW if both unclear.
- Output valid JSON only. No markdown. No explanation.

INPUT:
Name: {name}
Designation: {designation}
Company: {company}

Respond with ONLY this JSON:
{{"seniority_level":"string","industry_vertical":"string","company_size_estimate":"string","relevance_score":"string","relevance_reasoning":"string","inferred_pain_points":["string","string"],"enrichment_confidence":"string"}}"""

    result = {
        'seniority_level': 'Unknown',
        'industry_vertical': 'Unknown',
        'company_size_estimate': 'Unknown',
        'relevance_score': 'low',
        'relevance_reasoning': '',
        'inferred_pain_points': '',
        'enrichment_confidence': 'low'
    }

    try:
        resp = requests.post(ollama_url, json={
            'model': ollama_model,
            'prompt': prompt,
            'stream': False,
            'format': 'json',
            'options': {'temperature': 0.1, 'num_predict': 512}
        }, timeout=60)
        obj = json.loads(resp.json().get('response', '{}'))
        result['seniority_level'] = obj.get('seniority_level', 'Unknown')
        result['industry_vertical'] = obj.get('industry_vertical', 'Unknown')
        result['company_size_estimate'] = obj.get('company_size_estimate', 'Unknown')
        result['relevance_score'] = obj.get('relevance_score', 'low')
        result['relevance_reasoning'] = obj.get('relevance_reasoning', '')
        result['enrichment_confidence'] = obj.get('enrichment_confidence', 'low')
        pain = obj.get('inferred_pain_points', [])
        result['inferred_pain_points'] = ' | '.join(pain) if isinstance(pain, list) else str(pain)
    except Exception as e:
        result['relevance_reasoning'] = f'ERROR: {e}'

    return result
