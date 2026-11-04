from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db
import config
import json

# === Users ===

def create_user(username, password):
    db = get_db()
    db.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
               (username, generate_password_hash(password)))
    db.commit()
    user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    db.close()
    return dict(user)

def verify_user(username, password):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    db.close()
    if user and check_password_hash(user['password_hash'], password):
        return dict(user)
    return None

def get_user(user_id):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    db.close()
    return dict(user) if user else None

# === Campaigns ===

CAMPAIGN_FIELDS = ['name', 'description', 'campaign_type', 'status', 'enrichment_prompt',
    'persona_prompt', 'outreach_prompt', 'followup_prompt', 'soft_cta', 'banned_phrases',
    'email_signature', 'sender_name']

def create_campaign(user_id, data):
    db = get_db()
    fields = ['user_id']
    values = [user_id]
    for f in CAMPAIGN_FIELDS:
        if f in data:
            fields.append(f)
            values.append(data[f])
    placeholders = ','.join(['?'] * len(fields))
    cur = db.execute(f'INSERT INTO campaigns ({",".join(fields)}) VALUES ({placeholders})', values)
    db.commit()
    cid = cur.lastrowid
    db.close()
    return cid

def get_campaigns(user_id):
    db = get_db()
    rows = db.execute('''
        SELECT c.*,
            (SELECT COUNT(*) FROM contacts WHERE campaign_id = c.id) as contact_count,
            (SELECT COUNT(*) FROM email_tracking WHERE campaign_id = c.id) as sent_count,
            (SELECT COUNT(*) FROM email_tracking WHERE campaign_id = c.id AND replied_at IS NOT NULL) as reply_count
        FROM campaigns c WHERE c.user_id = ? ORDER BY c.updated_at DESC
    ''', (user_id,)).fetchall()
    db.close()
    return [dict(r) for r in rows]

def get_campaign(campaign_id):
    db = get_db()
    row = db.execute('SELECT * FROM campaigns WHERE id = ?', (campaign_id,)).fetchone()
    db.close()
    return dict(row) if row else None

def update_campaign(campaign_id, data):
    db = get_db()
    sets = []
    values = []
    for f in CAMPAIGN_FIELDS:
        if f in data:
            sets.append(f'{f} = ?')
            values.append(data[f])
    if not sets:
        db.close()
        return
    sets.append("updated_at = CURRENT_TIMESTAMP")
    values.append(campaign_id)
    db.execute(f'UPDATE campaigns SET {", ".join(sets)} WHERE id = ?', values)
    db.commit()
    db.close()

def delete_campaign(campaign_id):
    db = get_db()
    db.execute('DELETE FROM scheduled_jobs WHERE campaign_id = ?', (campaign_id,))
    db.execute('DELETE FROM pipeline_logs WHERE run_id IN (SELECT id FROM pipeline_runs WHERE campaign_id = ?)', (campaign_id,))
    db.execute('DELETE FROM pipeline_runs WHERE campaign_id = ?', (campaign_id,))
    db.execute('DELETE FROM followups WHERE campaign_id = ?', (campaign_id,))
    db.execute('DELETE FROM email_tracking WHERE campaign_id = ?', (campaign_id,))
    db.execute('DELETE FROM meetings WHERE campaign_id = ?', (campaign_id,))
    db.execute('DELETE FROM contacts WHERE campaign_id = ?', (campaign_id,))
    db.execute('DELETE FROM campaigns WHERE id = ?', (campaign_id,))
    db.commit()
    db.close()

# === Contacts ===

CONTACT_FIELDS = [
    'name', 'designation', 'company', 'profile_url', 'image_url', 'source_url',
    'scraped_at', 'seniority_level', 'industry_vertical', 'company_size_estimate',
    'relevance_score', 'relevance_reasoning', 'inferred_pain_points', 'enrichment_confidence',
    'linkedin_url', 'linkedin_status', 'persona', 'context_summary', 'personalization_themes',
    'recommended_tone', 'persona_confidence', 'tier', 'tier_score', 'assigned_to', 'channels',
    'routing_notes', 'downgrade_reason', 'email', 'email_confidence', 'email_status',
    'email_source', 'personal_email', 'email_subject', 'email_body', 'linkedin_message',
    'email_approved', 'email_sent'
]

def get_contacts(user_id, campaign_id, tier=None, search=None):
    db = get_db()
    query = 'SELECT * FROM contacts WHERE user_id = ? AND campaign_id = ?'
    params = [user_id, campaign_id]
    if tier:
        query += ' AND tier = ?'
        params.append(tier)
    if search:
        query += ' AND (LOWER(name) LIKE ? OR LOWER(company) LIKE ? OR LOWER(designation) LIKE ?)'
        s = f'%{search.lower()}%'
        params.extend([s, s, s])
    query += ' ORDER BY id DESC'
    rows = db.execute(query, params).fetchall()
    db.close()
    return [dict(r) for r in rows]

def get_contact(contact_id):
    db = get_db()
    row = db.execute('SELECT * FROM contacts WHERE id = ?', (contact_id,)).fetchone()
    db.close()
    return dict(row) if row else None

def create_contact(user_id, campaign_id, data):
    db = get_db()
    fields = ['user_id', 'campaign_id']
    values = [user_id, campaign_id]
    for f in CONTACT_FIELDS:
        if f in data and data[f] is not None:
            fields.append(f)
            values.append(data[f])
    placeholders = ','.join(['?'] * len(fields))
    cur = db.execute(f'INSERT INTO contacts ({",".join(fields)}) VALUES ({placeholders})', values)
    db.commit()
    cid = cur.lastrowid
    db.close()
    return cid

def update_contact(contact_id, data):
    db = get_db()
    sets = []
    values = []
    for f in CONTACT_FIELDS:
        if f in data:
            sets.append(f'{f} = ?')
            values.append(data[f])
    if not sets:
        db.close()
        return
    sets.append("updated_at = CURRENT_TIMESTAMP")
    values.append(contact_id)
    db.execute(f'UPDATE contacts SET {", ".join(sets)} WHERE id = ?', values)
    db.commit()
    db.close()

def delete_contacts(contact_ids):
    if not contact_ids:
        return
    db = get_db()
    placeholders = ','.join(['?'] * len(contact_ids))
    db.execute(f'DELETE FROM contacts WHERE id IN ({placeholders})', contact_ids)
    db.commit()
    db.close()

def bulk_create_contacts(user_id, campaign_id, contacts_list):
    db = get_db()
    created = 0
    for data in contacts_list:
        fields = ['user_id', 'campaign_id']
        values = [user_id, campaign_id]
        for f in CONTACT_FIELDS:
            if f in data and data[f] is not None and str(data[f]).strip():
                fields.append(f)
                values.append(data[f])
        if 'name' not in fields:
            continue
        placeholders = ','.join(['?'] * len(fields))
        db.execute(f'INSERT INTO contacts ({",".join(fields)}) VALUES ({placeholders})', values)
        created += 1
    db.commit()
    db.close()
    return created

# === Settings (global) ===

def get_setting(user_id, key):
    db = get_db()
    row = db.execute('SELECT value FROM settings WHERE user_id = ? AND key = ?', (user_id, key)).fetchone()
    db.close()
    return row['value'] if row else config.DEFAULTS.get(key, '')

def set_setting(user_id, key, value):
    db = get_db()
    db.execute('INSERT OR REPLACE INTO settings (user_id, key, value) VALUES (?, ?, ?)', (user_id, key, value))
    db.commit()
    db.close()

def set_settings_bulk(user_id, settings_dict):
    db = get_db()
    for key, value in settings_dict.items():
        db.execute('INSERT OR REPLACE INTO settings (user_id, key, value) VALUES (?, ?, ?)',
                   (user_id, key, str(value) if value is not None else ''))
    db.commit()
    db.close()

def get_all_settings(user_id):
    db = get_db()
    rows = db.execute('SELECT key, value FROM settings WHERE user_id = ?', (user_id,)).fetchall()
    db.close()
    settings = dict(config.DEFAULTS)
    for r in rows:
        settings[r['key']] = r['value']
    return settings

# === Email Tracking ===

def create_email_tracking(data):
    db = get_db()
    cur = db.execute('''INSERT INTO email_tracking
        (contact_id, user_id, campaign_id, email_type, message_id, resend_id, subject, body, sent_at, thread_position, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, 'sent')''',
        (data['contact_id'], data['user_id'], data.get('campaign_id'),
         data['email_type'], data.get('message_id', ''), data.get('resend_id', ''),
         data.get('subject', ''), data.get('body', ''), data.get('thread_position', 1)))
    db.commit()
    tid = cur.lastrowid
    db.close()
    return tid

def update_email_tracking(tracking_id, data):
    db = get_db()
    sets = []
    values = []
    for k, v in data.items():
        sets.append(f'{k} = ?')
        values.append(v)
    values.append(tracking_id)
    db.execute(f'UPDATE email_tracking SET {", ".join(sets)} WHERE id = ?', values)
    db.commit()
    db.close()

def get_email_tracking_for_contact(contact_id):
    db = get_db()
    rows = db.execute('SELECT * FROM email_tracking WHERE contact_id = ? ORDER BY sent_at', (contact_id,)).fetchall()
    db.close()
    return [dict(r) for r in rows]

def get_tracking_by_message_id(message_id):
    db = get_db()
    row = db.execute('SELECT * FROM email_tracking WHERE message_id = ?', (message_id,)).fetchone()
    db.close()
    return dict(row) if row else None

def get_tracking_by_resend_id(resend_id):
    db = get_db()
    row = db.execute('SELECT * FROM email_tracking WHERE resend_id = ?', (resend_id,)).fetchone()
    db.close()
    return dict(row) if row else None

def get_all_tracking(user_id, campaign_id=None):
    db = get_db()
    if campaign_id:
        rows = db.execute('''SELECT et.*, c.name as contact_name, c.company
            FROM email_tracking et JOIN contacts c ON et.contact_id = c.id
            WHERE et.user_id = ? AND et.campaign_id = ? ORDER BY et.sent_at DESC''', (user_id, campaign_id)).fetchall()
    else:
        rows = db.execute('''SELECT et.*, c.name as contact_name, c.company
            FROM email_tracking et JOIN contacts c ON et.contact_id = c.id
            WHERE et.user_id = ? ORDER BY et.sent_at DESC''', (user_id,)).fetchall()
    db.close()
    return [dict(r) for r in rows]

# === Follow-ups ===

def create_followup(data):
    db = get_db()
    cur = db.execute('''INSERT INTO followups
        (contact_id, user_id, campaign_id, parent_email_id, followup_number, subject, body)
        VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (data['contact_id'], data['user_id'], data.get('campaign_id'),
         data['parent_email_id'], data['followup_number'], data['subject'], data['body']))
    db.commit()
    fid = cur.lastrowid
    db.close()
    return fid

def get_followups(contact_id):
    db = get_db()
    rows = db.execute('SELECT * FROM followups WHERE contact_id = ? ORDER BY followup_number', (contact_id,)).fetchall()
    db.close()
    return [dict(r) for r in rows]

def get_followup_count(contact_id):
    db = get_db()
    row = db.execute('SELECT COUNT(*) as cnt FROM followups WHERE contact_id = ? AND sent = 1', (contact_id,)).fetchone()
    db.close()
    return row['cnt'] if row else 0

# === Meetings ===

def create_meeting(data):
    db = get_db()
    cur = db.execute('''INSERT INTO meetings
        (contact_id, user_id, campaign_id, title, datetime, duration_minutes, google_event_id, meet_link, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (data['contact_id'], data['user_id'], data.get('campaign_id'),
         data['title'], data['datetime'], data.get('duration_minutes', 30),
         data.get('google_event_id', ''), data.get('meet_link', ''), data.get('status', 'scheduled')))
    db.commit()
    db.close()
    return cur.lastrowid

def get_meetings(user_id, campaign_id=None):
    db = get_db()
    if campaign_id:
        rows = db.execute('''SELECT m.*, c.name as contact_name, c.company
            FROM meetings m JOIN contacts c ON m.contact_id = c.id
            WHERE m.user_id = ? AND m.campaign_id = ? ORDER BY m.datetime''', (user_id, campaign_id)).fetchall()
    else:
        rows = db.execute('''SELECT m.*, c.name as contact_name, c.company
            FROM meetings m JOIN contacts c ON m.contact_id = c.id
            WHERE m.user_id = ? ORDER BY m.datetime''', (user_id,)).fetchall()
    db.close()
    return [dict(r) for r in rows]

# === Pipeline ===

def create_pipeline_run(user_id, campaign_id, total, stages_config):
    db = get_db()
    cur = db.execute('''INSERT INTO pipeline_runs (user_id, campaign_id, total_contacts, stages_config, status)
        VALUES (?, ?, ?, ?, 'running')''', (user_id, campaign_id, total, json.dumps(stages_config)))
    db.commit()
    rid = cur.lastrowid
    db.close()
    return rid

def update_pipeline_run(run_id, data):
    db = get_db()
    sets = []
    values = []
    for k, v in data.items():
        sets.append(f'{k} = ?')
        values.append(v)
    values.append(run_id)
    db.execute(f'UPDATE pipeline_runs SET {", ".join(sets)} WHERE id = ?', values)
    db.commit()
    db.close()

def create_pipeline_log(run_id, contact_id, contact_name, stage, status, message):
    db = get_db()
    db.execute('''INSERT INTO pipeline_logs (run_id, contact_id, contact_name, stage, status, message)
        VALUES (?, ?, ?, ?, ?, ?)''', (run_id, contact_id, contact_name, stage, status, message))
    db.commit()
    db.close()

def get_pipeline_logs(run_id, after_id=0):
    db = get_db()
    rows = db.execute('SELECT * FROM pipeline_logs WHERE run_id = ? AND id > ? ORDER BY id', (run_id, after_id)).fetchall()
    db.close()
    return [dict(r) for r in rows]

def get_pipeline_run(run_id):
    db = get_db()
    row = db.execute('SELECT * FROM pipeline_runs WHERE id = ?', (run_id,)).fetchone()
    db.close()
    return dict(row) if row else None

# === Dashboard Stats ===

def get_dashboard_stats(user_id, campaign_id):
    db = get_db()
    def count(q, p=()):
        return db.execute(q, p).fetchone()[0]
    cid = campaign_id
    total = count('SELECT COUNT(*) FROM contacts WHERE user_id = ? AND campaign_id = ?', (user_id, cid))
    stats = {
        'total_contacts': total,
        'tier1': count("SELECT COUNT(*) FROM contacts WHERE user_id = ? AND campaign_id = ? AND tier = 'Tier 1'", (user_id, cid)),
        'tier2': count("SELECT COUNT(*) FROM contacts WHERE user_id = ? AND campaign_id = ? AND tier = 'Tier 2'", (user_id, cid)),
        'tier3': count("SELECT COUNT(*) FROM contacts WHERE user_id = ? AND campaign_id = ? AND tier = 'Tier 3'", (user_id, cid)),
        'enriched': count("SELECT COUNT(*) FROM contacts WHERE user_id = ? AND campaign_id = ? AND seniority_level != ''", (user_id, cid)),
        'linkedin_found': count("SELECT COUNT(*) FROM contacts WHERE user_id = ? AND campaign_id = ? AND linkedin_url != ''", (user_id, cid)),
        'personas_generated': count("SELECT COUNT(*) FROM contacts WHERE user_id = ? AND campaign_id = ? AND persona != ''", (user_id, cid)),
        'emails_found': count("SELECT COUNT(*) FROM contacts WHERE user_id = ? AND campaign_id = ? AND email != ''", (user_id, cid)),
        'outreach_generated': count("SELECT COUNT(*) FROM contacts WHERE user_id = ? AND campaign_id = ? AND email_subject != ''", (user_id, cid)),
        'emails_sent': count("SELECT COUNT(*) FROM email_tracking WHERE user_id = ? AND campaign_id = ?", (user_id, cid)),
        'delivered': count("SELECT COUNT(*) FROM email_tracking WHERE user_id = ? AND campaign_id = ? AND status = 'delivered'", (user_id, cid)),
        'opened': count("SELECT COUNT(*) FROM email_tracking WHERE user_id = ? AND campaign_id = ? AND status = 'opened'", (user_id, cid)),
        'replied': count("SELECT COUNT(*) FROM email_tracking WHERE user_id = ? AND campaign_id = ? AND status = 'replied'", (user_id, cid)),
        'bounced': count("SELECT COUNT(*) FROM email_tracking WHERE user_id = ? AND campaign_id = ? AND status = 'bounced'", (user_id, cid)),
        'followups_sent': count("SELECT COUNT(*) FROM followups WHERE user_id = ? AND campaign_id = ? AND sent = 1", (user_id, cid)),
        'meetings_scheduled': count("SELECT COUNT(*) FROM meetings WHERE user_id = ? AND campaign_id = ? AND status = 'scheduled'", (user_id, cid)),
    }
    safe = lambda n, d: round((n / d) * 100) if d > 0 else 0
    stats['enrichment_pct'] = safe(stats['enriched'], total)
    stats['linkedin_pct'] = safe(stats['linkedin_found'], total)
    stats['persona_pct'] = safe(stats['personas_generated'], total)
    stats['email_pct'] = safe(stats['emails_found'], total)
    stats['outreach_pct'] = safe(stats['outreach_generated'], total)
    db.close()
    return stats

def get_send_stats(user_id, campaign_id):
    db = get_db()
    def count(q, p=()):
        return db.execute(q, p).fetchone()[0]
    stats = {
        'ready': count("SELECT COUNT(*) FROM contacts WHERE user_id = ? AND campaign_id = ? AND email_approved = 1 AND email_sent = 0 AND email != ''", (user_id, campaign_id)),
        'sent': count("SELECT COUNT(*) FROM contacts WHERE user_id = ? AND campaign_id = ? AND email_sent = 1", (user_id, campaign_id)),
    }
    db.close()
    return stats

def get_tracking_stats(user_id, campaign_id):
    db = get_db()
    def count(q, p=()):
        return db.execute(q, p).fetchone()[0]
    stats = {
        'sent': count("SELECT COUNT(*) FROM email_tracking WHERE user_id = ? AND campaign_id = ?", (user_id, campaign_id)),
        'delivered': count("SELECT COUNT(*) FROM email_tracking WHERE user_id = ? AND campaign_id = ? AND delivered_at IS NOT NULL", (user_id, campaign_id)),
        'opened': count("SELECT COUNT(*) FROM email_tracking WHERE user_id = ? AND campaign_id = ? AND opened_at IS NOT NULL", (user_id, campaign_id)),
        'replied': count("SELECT COUNT(*) FROM email_tracking WHERE user_id = ? AND campaign_id = ? AND replied_at IS NOT NULL", (user_id, campaign_id)),
        'bounced': count("SELECT COUNT(*) FROM email_tracking WHERE user_id = ? AND campaign_id = ? AND bounced_at IS NOT NULL", (user_id, campaign_id)),
    }
    db.close()
    return stats

def get_followup_candidates(user_id, campaign_id, delay_days=3, max_followups=3):
    db = get_db()
    rows = db.execute('''
        SELECT et.contact_id, c.name as contact_name, c.company, et.id as tracking_id,
            et.sent_at as last_sent, et.open_count, et.message_id,
            CAST(julianday('now') - julianday(et.sent_at) AS INTEGER) as days_ago,
            (SELECT COUNT(*) FROM followups f WHERE f.contact_id = et.contact_id AND f.sent = 1) as sent_followups
        FROM email_tracking et
        JOIN contacts c ON et.contact_id = c.id
        WHERE et.user_id = ? AND et.campaign_id = ?
            AND et.replied_at IS NULL AND et.bounced_at IS NULL
            AND julianday('now') - julianday(et.sent_at) >= ?
        GROUP BY et.contact_id
        HAVING sent_followups < ?
        ORDER BY days_ago DESC
    ''', (user_id, campaign_id, delay_days, max_followups)).fetchall()
    db.close()
    result = []
    for r in rows:
        d = dict(r)
        d['next_followup_num'] = d['sent_followups'] + 1
        result.append(d)
    return result

def get_followup_candidates_for_auto(user_id, campaign_id, delay_days=3, max_followups=3):
    """Like get_followup_candidates but returns raw data needed for auto-scheduling."""
    db = get_db()
    rows = db.execute('''
        SELECT et.contact_id, c.name as contact_name, c.company, c.email,
            c.designation, et.id as tracking_id, et.subject as original_subject,
            et.body as original_body, et.message_id, et.open_count,
            CAST(julianday('now') - julianday(et.sent_at) AS INTEGER) as days_ago,
            (SELECT COUNT(*) FROM followups f WHERE f.contact_id = et.contact_id AND f.sent = 1) as sent_followups
        FROM email_tracking et
        JOIN contacts c ON et.contact_id = c.id
        WHERE et.user_id = ? AND et.campaign_id = ?
            AND et.replied_at IS NULL AND et.bounced_at IS NULL
            AND julianday('now') - julianday(et.sent_at) >= ?
        GROUP BY et.contact_id
        HAVING sent_followups < ?
        ORDER BY days_ago DESC
    ''', (user_id, campaign_id, delay_days, max_followups)).fetchall()
    db.close()
    return [dict(r) for r in rows]

# === Scheduled Jobs ===

def create_scheduled_job(user_id, campaign_id, job_type, scheduled_at, payload=None):
    db = get_db()
    cur = db.execute('''INSERT INTO scheduled_jobs (user_id, campaign_id, job_type, scheduled_at, payload)
        VALUES (?, ?, ?, ?, ?)''',
        (user_id, campaign_id, job_type, scheduled_at, json.dumps(payload or {})))
    db.commit()
    jid = cur.lastrowid
    db.close()
    return jid

def get_scheduled_jobs(user_id, campaign_id=None, status=None):
    db = get_db()
    query = 'SELECT * FROM scheduled_jobs WHERE user_id = ?'
    params = [user_id]
    if campaign_id:
        query += ' AND campaign_id = ?'
        params.append(campaign_id)
    if status:
        query += ' AND status = ?'
        params.append(status)
    query += ' ORDER BY scheduled_at ASC'
    rows = db.execute(query, params).fetchall()
    db.close()
    return [dict(r) for r in rows]

def get_pending_jobs(now_str):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM scheduled_jobs WHERE status = 'pending' AND scheduled_at <= ?",
        (now_str,)).fetchall()
    db.close()
    return [dict(r) for r in rows]

def update_scheduled_job(job_id, data):
    db = get_db()
    sets = []
    values = []
    for k, v in data.items():
        sets.append(f'{k} = ?')
        values.append(v)
    values.append(job_id)
    db.execute(f'UPDATE scheduled_jobs SET {", ".join(sets)} WHERE id = ?', values)
    db.commit()
    db.close()

def delete_scheduled_job(job_id):
    db = get_db()
    db.execute('DELETE FROM scheduled_jobs WHERE id = ?', (job_id,))
    db.commit()
    db.close()

def get_replied_contacts(user_id, campaign_id):
    db = get_db()
    rows = db.execute('''
        SELECT DISTINCT c.id, c.name, c.company
        FROM contacts c JOIN email_tracking et ON c.id = et.contact_id
        WHERE et.user_id = ? AND et.campaign_id = ? AND et.replied_at IS NOT NULL
    ''', (user_id, campaign_id)).fetchall()
    db.close()
    return [dict(r) for r in rows]
