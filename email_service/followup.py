import requests
import json
import re

def generate_followup(contact, original_email, followup_number, claude_api_key, claude_model, custom_prompt=None):
    tone_map = {
        1: "Gentle nudge. 2-3 sentences. Reference original email naturally. Don't be pushy.",
        2: "Add new value or insight. 2-3 sentences. Show you're thinking about their specific challenges.",
        3: "Breakup email. 1-2 sentences. Polite, give them an easy out. 'No worries if the timing isn't right.'"
    }
    tone = tone_map.get(followup_number, tone_map[1])

    prompt = f"""Write follow-up #{followup_number} for a sales email that got no reply.

RULES:
- {tone}
- Sound human, NOT like a template or AI.
- Don't repeat the original email content verbatim.
- Don't guilt trip or be passive-aggressive.
- Keep it SHORT.
- Output valid JSON only.

CONTEXT:
Recipient: {contact.get('name', '')} at {contact.get('company', '')}
Their role: {contact.get('designation', '')}
Original subject: {original_email.get('subject', '')}
Original email summary: {original_email.get('body', '')[:200]}

JSON:
{{"subject":"string","body":"string"}}"""

    try:
        resp = requests.post('https://api.anthropic.com/v1/messages',
            headers={
                'Content-Type': 'application/json',
                'x-api-key': claude_api_key,
                'anthropic-version': '2023-06-01'
            },
            json={
                'model': claude_model,
                'max_tokens': 300,
                'messages': [{'role': 'user', 'content': prompt}]
            },
            timeout=30)
        text = resp.json().get('content', [{}])[0].get('text', '{}')
        clean = re.sub(r'```json\n?', '', text)
        clean = re.sub(r'```\n?', '', clean).strip()
        obj = json.loads(clean)
        return {
            'subject': obj.get('subject', f'Re: {original_email.get("subject", "")}'),
            'body': obj.get('body', '')
        }
    except Exception as e:
        return {
            'subject': f'Re: {original_email.get("subject", "")}',
            'body': f'Generation failed: {e}'
        }
