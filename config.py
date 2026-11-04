import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SECRET_KEY = secrets.token_hex(32)
DATABASE = os.path.join(BASE_DIR, 'omega.db')

DEFAULTS = {
    'ollama_url': 'http://127.0.0.1:11434/api/generate',
    'ollama_model': 'llama3.1:8b',
    'claude_model': 'claude-sonnet-4-20250514',
    'claude_url': 'https://api.anthropic.com/v1/messages',
    'brave_url': 'https://api.search.brave.com/res/v1/web/search',
    'snov_auth_url': 'https://api.snov.io/v1/oauth/access_token',
    'resend_from_email': os.environ.get('OMEGA_FROM_EMAIL', ''),
    'reply_to_email': os.environ.get('OMEGA_REPLY_TO_EMAIL', ''),
    'sender_name': os.environ.get('OMEGA_SENDER_NAME', 'Your Name'),
    'email_signature': os.environ.get('OMEGA_EMAIL_SIGNATURE', 'Best,\nYour Name'),
    'email_font': 'Georgia, serif',
    'tier1_threshold': '70',
    'tier2_threshold': '40',
    'max_followups': '3',
    'followup_delay_days': '3',
}

DEFAULT_PROMPTS = {
    'event': {
        'enrichment_prompt': '',
        'persona_prompt': '',
        'outreach_prompt': '''You are a senior sales copywriter crafting outreach for a tech event/conference.

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
LinkedIn: {linkedin_url}

Write a warm, peer-to-peer outreach email referencing the event. Lead with VALUE, not a pitch.

Output ONLY valid JSON, no markdown:
{{"email_subject":"string","email_body":"3-5 sentences","linkedin_message":"under 280 chars"}}''',
        'followup_prompt': '',
        'soft_cta': '',
        'banned_phrases': 'hope this finds you well\njust reaching out\nquick question\npick your brain\nsynergy\ncircle back\nlow-hanging fruit\nleverage\nunlock\ngame-changer\nrevolutionary\nhope you are doing well\ntrust this email finds you',
    },
    'cold': {
        'enrichment_prompt': '',
        'persona_prompt': '',
        'outreach_prompt': '''You are a senior B2B sales copywriter crafting cold outreach emails.

STRICT RULES:
- Sound like a real human. NOT a template. NOT an AI.
- NEVER use: {banned_phrases}
- LinkedIn messages MUST be under 280 characters.
- Keep emails 3-5 sentences. Lead with a specific insight about their company or role.
- Subject lines must be specific and curiosity-driven. No generic subjects.
- End email body with soft CTA: "{soft_cta}"

CONTACT:
Name: {name}
Designation: {designation}
Company: {company}
Tier: {tier} (Score: {tier_score}/100)
Persona: {persona}
Context: {context_summary}
Themes: {personalization_themes}

Write a direct, value-driven cold email. Reference something specific about their company or role. No event references.

Output ONLY valid JSON, no markdown:
{{"email_subject":"string","email_body":"3-5 sentences","linkedin_message":"under 280 chars"}}''',
        'followup_prompt': '',
        'soft_cta': '',
        'banned_phrases': 'hope this finds you well\njust reaching out\nquick question\npick your brain\nsynergy\ncircle back\nlow-hanging fruit\nleverage\nunlock\ngame-changer\nrevolutionary',
    },
    'nurture': {
        'enrichment_prompt': '',
        'persona_prompt': '',
        'outreach_prompt': '''You are writing a warm, educational outreach email to nurture a relationship with a potential lead.

STRICT RULES:
- Sound genuinely helpful. Share value, not a pitch.
- NEVER use: {banned_phrases}
- LinkedIn messages MUST be under 280 characters.
- Keep emails 3-5 sentences. Lead with an insight, resource, or observation relevant to their work.
- Tone: consultative, peer-to-peer, not salesy.
- End email body with soft CTA: "{soft_cta}"

CONTACT:
Name: {name}
Designation: {designation}
Company: {company}
Persona: {persona}
Context: {context_summary}
Themes: {personalization_themes}

Write a nurture email that provides genuine value. Could be sharing a relevant insight, congratulating on something, or offering a useful resource.

Output ONLY valid JSON, no markdown:
{{"email_subject":"string","email_body":"3-5 sentences","linkedin_message":"under 280 chars"}}''',
        'followup_prompt': '',
        'soft_cta': '',
        'banned_phrases': 'hope this finds you well\njust reaching out\nsynergy\ncircle back\nlow-hanging fruit',
    },
    'custom': {
        'enrichment_prompt': '',
        'persona_prompt': '',
        'outreach_prompt': '',
        'followup_prompt': '',
        'soft_cta': '',
        'banned_phrases': '',
    }
}
