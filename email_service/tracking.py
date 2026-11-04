"""
Tracking via Resend API polling + IMAP reply detection.
No webhooks needed — everything runs locally.
"""
import re
import imaplib
import email as email_lib
from email.header import decode_header
from datetime import datetime
import requests
import models

RESEND_API = 'https://api.resend.com/emails'


def poll_resend_status(api_key, user_id):
    """Poll Resend API for delivery status of all tracked emails."""
    all_tracking = models.get_all_tracking(user_id)
    updated = 0

    for t in all_tracking:
        # Skip already replied/bounced (final states)
        if t['status'] in ('replied', 'bounced', 'complained'):
            continue
        resend_id = t.get('resend_id', '')
        if not resend_id:
            continue

        try:
            resp = requests.get(
                f'{RESEND_API}/{resend_id}',
                headers={'Authorization': f'Bearer {api_key}'},
                timeout=10
            )
            if resp.status_code != 200:
                continue

            data = resp.json()
            updates = {}
            now = datetime.now().isoformat()

            # Resend returns: last_event can be "delivered", "opened", "clicked", "bounced", "complained"
            last_event = data.get('last_event', '')

            if last_event == 'delivered' and t['status'] == 'sent':
                updates['delivered_at'] = data.get('delivered_at') or now
                updates['status'] = 'delivered'

            elif last_event == 'opened':
                if not t.get('opened_at'):
                    updates['opened_at'] = data.get('opened_at') or now
                # Count opens from Resend
                opens = len(data.get('opens', []) or [])
                if opens > t.get('open_count', 0):
                    updates['open_count'] = opens
                updates['status'] = 'opened'
                # Also mark delivered if not yet
                if not t.get('delivered_at'):
                    updates['delivered_at'] = data.get('delivered_at') or now

            elif last_event == 'clicked':
                if not t.get('clicked_at'):
                    updates['clicked_at'] = data.get('clicked_at') or now
                if t['status'] != 'replied':
                    updates['status'] = 'clicked'

            elif last_event == 'bounced':
                updates['bounced_at'] = data.get('bounced_at') or now
                updates['status'] = 'bounced'

            elif last_event == 'complained':
                updates['status'] = 'complained'

            if updates:
                models.update_email_tracking(t['id'], updates)
                updated += 1

        except Exception:
            continue

    return {'updated': updated, 'total_checked': len(all_tracking)}


def check_imap_replies(imap_host, imap_email, imap_password, user_id, imap_port=993):
    """Check inbox via IMAP for replies to sent emails.
    Matches replies by:
    1. In-Reply-To header matching our sent Message-IDs
    2. Subject line matching "Re: {our subject}"
    3. Sender email matching a contact's email
    """
    found_replies = 0

    try:
        mail = imaplib.IMAP4_SSL(imap_host, imap_port)
        mail.login(imap_email, imap_password)
        mail.select('INBOX')

        # Search for recent unread emails
        status, messages = mail.search(None, 'UNSEEN')
        if status != 'OK' or not messages[0]:
            mail.logout()
            return {'found': 0, 'checked': 0}

        msg_ids = messages[0].split()
        checked = 0

        # Get all our sent message IDs for matching
        all_tracking = models.get_all_tracking(user_id)
        sent_message_ids = {}  # message_id -> tracking record
        sent_resend_ids = {}
        contact_emails = {}  # email -> tracking record

        for t in all_tracking:
            if t.get('message_id'):
                sent_message_ids[t['message_id']] = t
                # Also store without angle brackets
                clean = t['message_id'].strip('<>')
                sent_message_ids[clean] = t
            if t.get('resend_id'):
                sent_resend_ids[t['resend_id']] = t
            # Map contact email to most recent tracking
            contact = models.get_contact(t['contact_id'])
            if contact and contact.get('email'):
                contact_emails[contact['email'].lower()] = t

        for msg_id in msg_ids[-50:]:  # Check last 50 unread
            checked += 1
            try:
                status, msg_data = mail.fetch(msg_id, '(RFC822)')
                if status != 'OK':
                    continue

                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)

                # Extract fields
                from_addr = _extract_email(msg.get('From', ''))
                subject = _decode_header(msg.get('Subject', ''))
                in_reply_to = (msg.get('In-Reply-To') or '').strip().strip('<>')
                references = (msg.get('References') or '').strip()

                # Extract body
                body_text = _get_body(msg)

                # Method 1: Match In-Reply-To header
                tracking = None
                if in_reply_to:
                    tracking = sent_message_ids.get(in_reply_to)
                    if not tracking:
                        # Check references header
                        for ref in references.split():
                            ref_clean = ref.strip('<>')
                            tracking = sent_message_ids.get(ref_clean)
                            if tracking:
                                break

                # Method 2: Match by sender email
                if not tracking and from_addr:
                    tracking = contact_emails.get(from_addr.lower())

                # Method 3: Match +{id}@ in To address (e.g. you+123@example.com)
                if not tracking:
                    to_addr = msg.get('To', '')
                    match = re.search(r'[a-zA-Z0-9._%+-]+\+(\d+)@', to_addr)
                    if match:
                        cid = int(match.group(1))
                        trackings = models.get_email_tracking_for_contact(cid)
                        if trackings:
                            tracking = trackings[-1]

                if tracking and tracking['status'] != 'replied':
                    models.update_email_tracking(tracking['id'], {
                        'replied_at': datetime.now().isoformat(),
                        'reply_content': body_text[:5000],
                        'status': 'replied'
                    })
                    found_replies += 1

            except Exception:
                continue

        mail.logout()

    except imaplib.IMAP4.error as e:
        return {'found': 0, 'error': f'IMAP login failed: {e}'}
    except Exception as e:
        return {'found': 0, 'error': str(e)}

    return {'found': found_replies, 'checked': checked}


def _extract_email(from_str):
    """Extract email address from 'Name <email>' format."""
    match = re.search(r'<([^>]+)>', from_str)
    if match:
        return match.group(1)
    if '@' in from_str:
        return from_str.strip()
    return ''

def _decode_header(header):
    """Decode email header."""
    if not header:
        return ''
    parts = decode_header(header)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or 'utf-8', errors='replace'))
        else:
            decoded.append(part)
    return ''.join(decoded)

def _get_body(msg):
    """Extract text body from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == 'text/plain':
                try:
                    return part.get_payload(decode=True).decode('utf-8', errors='replace')
                except Exception:
                    pass
            elif content_type == 'text/html':
                try:
                    return part.get_payload(decode=True).decode('utf-8', errors='replace')
                except Exception:
                    pass
    else:
        try:
            return msg.get_payload(decode=True).decode('utf-8', errors='replace')
        except Exception:
            pass
    return ''
