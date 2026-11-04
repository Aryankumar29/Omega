import requests
import re
import base64
import os

RESEND_API_URL = 'https://api.resend.com/emails'

def format_email_html(body_text, recipient_first_name, signature='Best regards,\nYour Name', font='Georgia, serif'):
    # Strip any greeting the LLM added — we add our own
    body_clean = re.sub(r'^(Hi|Hey|Hello|Dear)\s+\w+[,.]?\s*\n?', '', body_text.strip(), flags=re.I).strip()

    # Strip any sign-off the LLM added — we use the campaign signature instead
    body_clean = re.sub(
        r'\n*(Best regards?|Best|Regards|Warm regards|Cheers|Thanks|Thank you)[,.]?\s*\n.*$',
        '', body_clean, flags=re.I | re.DOTALL
    ).strip()

    sig_html = signature.replace('\n', '<br>')
    body_paragraphs = body_clean.replace('\n\n', '</p><p>').replace('\n', '<br>')
    return f'''<div style="font-family: {font}; font-size: 14px; color: #333; max-width: 600px; line-height: 1.6;">
<p>Hi {recipient_first_name},</p>
<p>{body_paragraphs}</p>
<br>
<p>{sig_html}</p>
</div>'''

def _build_attachments(file_paths):
    """Convert file paths to Resend attachment format (base64 encoded)."""
    attachments = []
    for path in file_paths:
        if not path or not os.path.exists(path):
            continue
        filename = os.path.basename(path)
        with open(path, 'rb') as f:
            content = base64.b64encode(f.read()).decode('utf-8')
        attachments.append({
            'filename': filename,
            'content': content
        })
    return attachments

def send_email(api_key, from_email, to_email, subject, body_html, reply_to=None, headers=None, sender_name='Your Name', attachments=None):
    payload = {
        'from': f'{sender_name} <{from_email}>',
        'to': [to_email],
        'subject': subject,
        'html': body_html,
    }
    if reply_to:
        payload['reply_to'] = reply_to
    if headers:
        payload['headers'] = headers
    if attachments:
        payload['attachments'] = attachments

    resp = requests.post(RESEND_API_URL,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        },
        json=payload,
        timeout=30)

    data = resp.json()
    if resp.status_code >= 400:
        raise Exception(f"Resend error: {data.get('message', resp.text)}")

    return {
        'id': data.get('id', ''),
        'message_id': data.get('id', '')
    }

def send_threaded_followup(api_key, from_email, to_email, subject, body_html, original_message_id, reply_to=None, sender_name='Your Name', attachments=None):
    clean_subject = re.sub(r'^(Re:\s*)+', '', subject, flags=re.I).strip()
    threaded_subject = f'Re: {clean_subject}'

    headers = {}
    if original_message_id:
        msg_id = original_message_id
        if not msg_id.startswith('<'):
            msg_id = f'<{msg_id}>'
        headers['In-Reply-To'] = msg_id
        headers['References'] = msg_id

    return send_email(
        api_key=api_key, from_email=from_email, to_email=to_email,
        subject=threaded_subject, body_html=body_html, reply_to=reply_to,
        headers=headers, sender_name=sender_name, attachments=attachments
    )
