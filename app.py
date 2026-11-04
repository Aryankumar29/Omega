import os
import sys
import json
import threading
import time
from datetime import datetime, timedelta
from functools import wraps

import pandas as pd
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, jsonify, Response, send_file)

import config
from database import init_db, get_db
import models
from pipeline.runner import run_pipeline
from email_service.resend_client import send_email, send_threaded_followup, format_email_html, _build_attachments
from email_service.tracking import poll_resend_status, check_imap_replies
from email_service.followup import generate_followup
from calendar_service.google_cal import (get_auth_url, handle_callback,
                                          get_free_slots, create_meeting as gcal_create_meeting, refresh_token)

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

pipeline_state = {}

# === Auth ===
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def get_campaign_or_404(cid):
    campaign = models.get_campaign(cid)
    if not campaign:
        return None
    return campaign

# ============================================================
#  AUTH
# ============================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = models.verify_user(request.form.get('username', '').strip(), request.form.get('password', ''))
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect('/campaigns')
        flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if password != request.form.get('password2', ''):
            flash('Passwords do not match', 'error')
        elif not username or not password:
            flash('Username and password required', 'error')
        else:
            try:
                models.create_user(username, password)
                flash('Account created!', 'success')
                return redirect(url_for('login'))
            except Exception:
                flash('Username already taken', 'error')
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ============================================================
#  CAMPAIGNS
# ============================================================

@app.route('/')
@login_required
def index():
    return redirect('/campaigns')

@app.route('/campaigns')
@login_required
def campaigns():
    campaign_list = models.get_campaigns(session['user_id'])
    return render_template('campaigns.html', campaigns=campaign_list, campaign=None, active_page='campaigns')

@app.route('/campaigns/create', methods=['POST'])
@login_required
def create_campaign():
    data = request.get_json()
    ctype = data.get('campaign_type', 'event')
    defaults = config.DEFAULT_PROMPTS.get(ctype, config.DEFAULT_PROMPTS['custom'])
    campaign_data = {
        'name': data.get('name', 'Untitled Campaign'),
        'description': data.get('description', ''),
        'campaign_type': ctype,
        **defaults
    }
    cid = models.create_campaign(session['user_id'], campaign_data)
    return jsonify({'success': True, 'id': cid})

# ============================================================
#  CAMPAIGN SCOPED ROUTES — /c/<cid>/...
# ============================================================

@app.route('/c/<int:cid>/')
@login_required
def campaign_dashboard(cid):
    campaign = get_campaign_or_404(cid)
    if not campaign:
        return redirect('/campaigns')
    stats = models.get_dashboard_stats(session['user_id'], cid)
    return render_template('dashboard.html', campaign=campaign, stats=stats, active_page='dashboard')

@app.route('/c/<int:cid>/edit')
@login_required
def campaign_edit(cid):
    campaign = get_campaign_or_404(cid)
    if not campaign:
        return redirect('/campaigns')
    return render_template('campaign_edit.html', campaign=campaign, default_prompts=config.DEFAULT_PROMPTS, active_page='campaign_edit')

@app.route('/c/<int:cid>/update', methods=['PUT'])
@login_required
def campaign_update(cid):
    try:
        data = request.get_json()
        models.update_campaign(cid, data)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/c/<int:cid>/delete', methods=['DELETE'])
@login_required
def campaign_delete(cid):
    models.delete_campaign(cid)
    return jsonify({'success': True})

# === Contacts ===

@app.route('/c/<int:cid>/contacts')
@login_required
def campaign_contacts(cid):
    campaign = get_campaign_or_404(cid)
    if not campaign:
        return redirect('/campaigns')
    contact_list = models.get_contacts(session['user_id'], cid)
    return render_template('contacts.html', campaign=campaign, contacts=contact_list, active_page='contacts')

@app.route('/c/<int:cid>/contacts/<int:contact_id>', methods=['GET'])
@login_required
def get_contact(cid, contact_id):
    c = models.get_contact(contact_id)
    return jsonify(c) if c else (jsonify({'error': 'Not found'}), 404)

@app.route('/c/<int:cid>/contacts/upload', methods=['POST'])
@login_required
def upload_contacts(cid):
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'No file'}), 400
    try:
        df = pd.read_csv(file) if file.filename.endswith('.csv') else pd.read_excel(file)
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]
    if request.form.get('preview') == 'true':
        columns = {col: {'fill_pct': round((df[col].notna().sum() / len(df)) * 100) if len(df) > 0 else 0} for col in df.columns}
        return jsonify({
            'total_rows': len(df), 'columns': columns,
            'has_email': int(df['email'].notna().sum()) if 'email' in df.columns else 0,
            'has_linkedin': int(df['linkedin_url'].notna().sum()) if 'linkedin_url' in df.columns else 0,
        })
    records = df.where(pd.notna(df), '').to_dict('records')
    count = models.bulk_create_contacts(session['user_id'], cid, records)
    return jsonify({'success': True, 'imported': count})

@app.route('/c/<int:cid>/contacts/add', methods=['POST'])
@login_required
def add_contact(cid):
    data = request.get_json()
    if not data.get('name'):
        return jsonify({'error': 'Name required'}), 400
    contact_id = models.create_contact(session['user_id'], cid, data)
    return jsonify({'success': True, 'id': contact_id})

@app.route('/c/<int:cid>/contacts/<int:contact_id>', methods=['PUT'])
@login_required
def update_contact(cid, contact_id):
    models.update_contact(contact_id, request.get_json())
    return jsonify({'success': True})

@app.route('/c/<int:cid>/contacts/delete', methods=['DELETE'])
@login_required
def delete_contacts_route(cid):
    ids = [int(i) for i in request.get_json().get('ids', [])]
    models.delete_contacts(ids)
    return jsonify({'success': True})

@app.route('/c/<int:cid>/contacts/export')
@login_required
def export_contacts(cid):
    contacts = models.get_contacts(session['user_id'], cid)
    df = pd.DataFrame(contacts)
    path = os.path.join(config.BASE_DIR, 'export_contacts.csv')
    df.to_csv(path, index=False)
    return send_file(path, as_attachment=True, download_name='omega_contacts.csv')

# === Pipeline ===

@app.route('/c/<int:cid>/pipeline')
@login_required
def campaign_pipeline(cid):
    campaign = get_campaign_or_404(cid)
    if not campaign:
        return redirect('/campaigns')
    uid = session['user_id']
    total = len(models.get_contacts(uid, cid))
    db = get_db()
    stage_stats = {}
    for stage, field in [('enrichment','seniority_level'),('linkedin','linkedin_url'),('persona','persona'),
                          ('segmentation','tier'),('email_finder','email'),('outreach','email_subject')]:
        done = db.execute(f"SELECT COUNT(*) FROM contacts WHERE user_id = ? AND campaign_id = ? AND {field} != ''", (uid, cid)).fetchone()[0]
        stage_stats[stage] = f'{done}/{total} completed'
    stage_stats['dedup'] = f'{total} contacts'
    db.close()
    return render_template('pipeline.html', campaign=campaign, total_contacts=total, stage_stats=stage_stats, active_page='pipeline')

@app.route('/c/<int:cid>/pipeline/run', methods=['POST'])
@login_required
def run_pipeline_route(cid):
    uid = session['user_id']
    campaign = get_campaign_or_404(cid)
    data = request.get_json()
    stages = data.get('stages', {})
    target = data.get('target', 'all')

    all_contacts = models.get_contacts(uid, cid)
    if target == 'tier1': all_contacts = [c for c in all_contacts if c.get('tier') == 'Tier 1']
    elif target == 'tier2': all_contacts = [c for c in all_contacts if c.get('tier') == 'Tier 2']
    elif target == 'tier3': all_contacts = [c for c in all_contacts if c.get('tier') == 'Tier 3']
    elif target == 'unscored': all_contacts = [c for c in all_contacts if not c.get('tier')]

    run_id = models.create_pipeline_run(uid, cid, len(all_contacts), stages)
    settings = models.get_all_settings(uid)

    pipeline_state[run_id] = {
        'status': 'running',
        'stage_progress': {s: {'total': len(all_contacts), 'done': 0} for s in stages},
        'logs': [], 'stop_requested': False
    }

    def background_run():
        def log_cb(contact_id, cname, stage, status, message):
            if pipeline_state.get(run_id, {}).get('stop_requested'):
                raise StopIteration()
            models.create_pipeline_log(run_id, contact_id, cname, stage, status, message)
            pipeline_state[run_id]['logs'].append({
                'time': datetime.now().strftime('%H:%M:%S'), 'stage': stage,
                'contact_name': cname, 'status': status, 'message': message
            })
            if stage in pipeline_state[run_id]['stage_progress'] and status in ('success', 'skipped'):
                pipeline_state[run_id]['stage_progress'][stage]['done'] += 1

        try:
            processed, summary = run_pipeline(all_contacts, stages, settings, campaign=campaign, log_callback=log_cb)
            for c in processed:
                if c.get('id'):
                    models.update_contact(c['id'], c)
            models.update_pipeline_run(run_id, {'status': 'completed', 'completed_at': datetime.now().isoformat()})
            pipeline_state[run_id]['status'] = 'completed'
        except StopIteration:
            models.update_pipeline_run(run_id, {'status': 'stopped'})
            pipeline_state[run_id]['status'] = 'stopped'
        except Exception as e:
            models.update_pipeline_run(run_id, {'status': 'failed'})
            pipeline_state[run_id]['status'] = 'failed'
            pipeline_state[run_id]['logs'].append({
                'time': datetime.now().strftime('%H:%M:%S'), 'stage': 'system',
                'contact_name': '', 'status': 'error', 'message': str(e)
            })

    threading.Thread(target=background_run, daemon=True).start()
    return jsonify({'run_id': run_id})

@app.route('/c/<int:cid>/pipeline/status/<int:run_id>')
@login_required
def pipeline_status(cid, run_id):
    state = pipeline_state.get(run_id)
    if not state:
        run = models.get_pipeline_run(run_id)
        return jsonify({'status': run['status'] if run else 'not_found'})
    last_seen = int(request.args.get('last_log', 0))
    return jsonify({
        'status': state['status'], 'stage_progress': state['stage_progress'],
        'new_logs': state['logs'][last_seen:], 'total_logs': len(state['logs'])
    })

@app.route('/c/<int:cid>/pipeline/stop/<int:run_id>', methods=['POST'])
@login_required
def stop_pipeline(cid, run_id):
    if run_id in pipeline_state:
        pipeline_state[run_id]['stop_requested'] = True
    return jsonify({'success': True})

@app.route('/c/<int:cid>/pipeline/run-single/<int:contact_id>/<stage>', methods=['POST'])
@login_required
def run_single_stage(cid, contact_id, stage):
    contact = models.get_contact(contact_id)
    if not contact:
        return jsonify({'error': 'Not found'}), 404
    campaign = get_campaign_or_404(cid)
    settings = models.get_all_settings(session['user_id'])
    try:
        processed, _ = run_pipeline([contact], {stage: 'all'}, settings, campaign=campaign)
        if processed:
            models.update_contact(contact_id, processed[0])
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# === Email Review ===

@app.route('/c/<int:cid>/emails/review')
@login_required
def email_review(cid):
    campaign = get_campaign_or_404(cid)
    if not campaign:
        return redirect('/campaigns')
    contacts = models.get_contacts(session['user_id'], cid)
    emails = [c for c in contacts if c.get('email_subject')]
    return render_template('email_review.html', campaign=campaign, emails=emails, active_page='email_review')

@app.route('/c/<int:cid>/emails/approve/<int:contact_id>', methods=['PUT'])
@login_required
def approve_email(cid, contact_id):
    models.update_contact(contact_id, {'email_approved': 1})
    return jsonify({'success': True})

@app.route('/c/<int:cid>/emails/approve-bulk', methods=['PUT'])
@login_required
def approve_bulk(cid):
    ids = request.get_json().get('ids', [])
    for contact_id in ids:
        models.update_contact(contact_id, {'email_approved': 1})
    return jsonify({'success': True, 'count': len(ids)})

@app.route('/c/<int:cid>/emails/regenerate/<int:contact_id>', methods=['POST'])
@login_required
def regenerate_email(cid, contact_id):
    contact = models.get_contact(contact_id)
    if not contact:
        return jsonify({'error': 'Not found'}), 404
    campaign = get_campaign_or_404(cid)
    settings = models.get_all_settings(session['user_id'])
    try:
        processed, _ = run_pipeline([contact], {'outreach': 'all'}, settings, campaign=campaign)
        if processed:
            models.update_contact(contact_id, processed[0])
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/c/<int:cid>/emails/edit/<int:contact_id>', methods=['PUT'])
@login_required
def edit_email(cid, contact_id):
    models.update_contact(contact_id, request.get_json())
    return jsonify({'success': True})

# === Attachments ===

UPLOAD_DIR = os.path.join(config.BASE_DIR, 'uploads')

def get_campaign_attachments_dir(cid):
    d = os.path.join(UPLOAD_DIR, str(cid))
    os.makedirs(d, exist_ok=True)
    return d

def get_campaign_attachment_files(cid):
    d = get_campaign_attachments_dir(cid)
    files = []
    for f in os.listdir(d):
        path = os.path.join(d, f)
        if os.path.isfile(path):
            size_kb = round(os.path.getsize(path) / 1024, 1)
            files.append({'name': f, 'path': path, 'size_kb': size_kb})
    return files

def get_campaign_resend_attachments(cid):
    files = get_campaign_attachment_files(cid)
    return _build_attachments([f['path'] for f in files])

@app.route('/c/<int:cid>/attachments')
@login_required
def list_attachments(cid):
    return jsonify({'files': get_campaign_attachment_files(cid)})

@app.route('/c/<int:cid>/attachments/upload', methods=['POST'])
@login_required
def upload_attachment(cid):
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'No filename'}), 400
    # Limit to 10MB
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > 10 * 1024 * 1024:
        return jsonify({'error': 'File too large (max 10MB)'}), 400
    d = get_campaign_attachments_dir(cid)
    safe_name = file.filename.replace('..', '').replace('/', '').replace('\\', '')
    file.save(os.path.join(d, safe_name))
    return jsonify({'success': True, 'name': safe_name, 'size_kb': round(size / 1024, 1)})

@app.route('/c/<int:cid>/attachments/delete', methods=['POST'])
@login_required
def delete_attachment(cid):
    data = request.get_json()
    filename = data.get('filename', '')
    safe_name = filename.replace('..', '').replace('/', '').replace('\\', '')
    path = os.path.join(get_campaign_attachments_dir(cid), safe_name)
    if os.path.exists(path):
        os.remove(path)
    return jsonify({'success': True})

# === Send & Track ===

@app.route('/c/<int:cid>/send')
@login_required
def send_track(cid):
    campaign = get_campaign_or_404(cid)
    if not campaign:
        return redirect('/campaigns')
    uid = session['user_id']
    settings = models.get_all_settings(uid)
    send_stats = models.get_send_stats(uid, cid)
    tracking_stats = models.get_tracking_stats(uid, cid)
    tracking = models.get_all_tracking(uid, cid)
    delay = int(settings.get('followup_delay_days', 3))
    max_fu = int(settings.get('max_followups', 3))
    candidates = models.get_followup_candidates(uid, cid, delay, max_fu)
    attachments = get_campaign_attachment_files(cid)
    scheduled_jobs = models.get_scheduled_jobs(uid, cid)
    return render_template('send_track.html', campaign=campaign, send_stats=send_stats,
        tracking_stats=tracking_stats, tracking=tracking, followup_candidates=candidates,
        followup_delay=delay, max_followups=max_fu, attachments=attachments,
        scheduled_jobs=scheduled_jobs, active_page='send_track')

@app.route('/c/<int:cid>/send/emails', methods=['POST'])
@login_required
def send_emails(cid):
    uid = session['user_id']
    settings = models.get_all_settings(uid)
    campaign = get_campaign_or_404(cid)
    api_key = settings.get('resend_api_key', '')
    from_email = settings.get('resend_from_email', '')
    reply_to_base = settings.get('reply_to_email', '')
    sender_name = campaign.get('sender_name') or settings.get('sender_name', 'Your Name')
    signature = campaign.get('email_signature') or settings.get('email_signature', 'Best,\nYour Name')
    font = settings.get('email_font', 'Georgia, serif')
    campaign_attachments = get_campaign_resend_attachments(cid)
    contacts = models.get_contacts(uid, cid)
    ready = [c for c in contacts if c.get('email_approved') and not c.get('email_sent') and c.get('email')]

    def stream():
        if not api_key:
            yield f'data:{json.dumps({"status":"error","message":"Resend API key not set","name":"","time":datetime.now().strftime("%H:%M:%S")})}\n\n'
            return

        for c in ready:
            try:
                subject = c.get('email_subject', '')
                body = c.get('email_body', '')
                first_name = c['name'].split()[0] if c.get('name') else ''
                body_html = format_email_html(body, first_name, signature, font)
                rt_user, rt_domain = reply_to_base.split('@')
                reply_to = f"{rt_user}+{c['id']}@{rt_domain}"

                result = send_email(api_key, from_email, c['email'], subject, body_html,
                                   reply_to=reply_to, sender_name=sender_name,
                                   attachments=campaign_attachments if campaign_attachments else None)

                models.create_email_tracking({
                    'contact_id': c['id'], 'user_id': uid, 'campaign_id': cid,
                    'email_type': 'outreach',
                    'message_id': result.get('message_id', result.get('id', '')),
                    'resend_id': result.get('id', ''),
                    'subject': subject, 'body': body, 'thread_position': 1
                })
                models.update_contact(c['id'], {'email_sent': 1})
                yield f'data:{json.dumps({"status":"success","name":c["name"],"message":f"Sent to {c["email"]}","time":datetime.now().strftime("%H:%M:%S")})}\n\n'
                time.sleep(0.5)
            except Exception as e:
                yield f'data:{json.dumps({"status":"error","name":c.get("name",""),"message":str(e),"time":datetime.now().strftime("%H:%M:%S")})}\n\n'

        yield f'data:{json.dumps({"status":"complete","name":"","message":"Done","time":datetime.now().strftime("%H:%M:%S")})}\n\n'

    return Response(stream(), mimetype='text/event-stream')

@app.route('/c/<int:cid>/send/test', methods=['POST'])
@login_required
def send_test(cid):
    settings = models.get_all_settings(session['user_id'])
    api_key = settings.get('resend_api_key', '')
    from_email = settings.get('resend_from_email', '')
    if not api_key:
        return jsonify({'error': 'Resend API key not set'}), 400
    try:
        body_html = format_email_html('Test email from Omega. If you see this, sending works.', 'there',
            settings.get('email_signature', 'Best,\nYour Name'), settings.get('email_font', 'Georgia, serif'))
        test_to = settings.get('reply_to_email', '')
        send_email(api_key, from_email, test_to, '[TEST] Omega test', body_html,
                   sender_name=settings.get('sender_name', 'Your Name'))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/send/tracking-updates')
@login_required
def tracking_updates():
    uid = session['user_id']
    settings = models.get_all_settings(uid)
    result = {'resend': {}, 'imap': {}}
    api_key = settings.get('resend_api_key', '')
    if api_key:
        result['resend'] = poll_resend_status(api_key, uid)
    imap_host = settings.get('imap_host', '')
    imap_email = settings.get('imap_email', '')
    imap_password = settings.get('imap_password', '')
    if imap_host and imap_email and imap_password:
        result['imap'] = check_imap_replies(imap_host, imap_email, imap_password, uid, int(settings.get('imap_port', '993')))
    result['has_updates'] = (result['resend'].get('updated', 0) > 0 or result['imap'].get('found', 0) > 0)
    return jsonify(result)

@app.route('/c/<int:cid>/send/followup/generate/<int:contact_id>', methods=['POST'])
@login_required
def generate_followup_route(cid, contact_id):
    contact = models.get_contact(contact_id)
    if not contact:
        return jsonify({'error': 'Not found'}), 404
    settings = models.get_all_settings(session['user_id'])
    campaign = get_campaign_or_404(cid)
    trackings = models.get_email_tracking_for_contact(contact_id)
    if not trackings:
        return jsonify({'error': 'No email sent yet'}), 400
    original = trackings[-1]
    fu_count = models.get_followup_count(contact_id)
    result = generate_followup(contact, original, fu_count + 1,
        settings.get('claude_api_key', ''), settings.get('claude_model', ''),
        custom_prompt=(campaign or {}).get('followup_prompt', ''))
    return jsonify({'success': True, 'subject': result['subject'], 'body': result['body'], 'contact_name': contact['name']})

@app.route('/c/<int:cid>/send/followup/<int:contact_id>', methods=['POST'])
@login_required
def send_followup_route(cid, contact_id):
    data = request.get_json()
    contact = models.get_contact(contact_id)
    if not contact:
        return jsonify({'error': 'Not found'}), 404
    settings = models.get_all_settings(session['user_id'])
    api_key = settings.get('resend_api_key', '')
    if not api_key:
        return jsonify({'error': 'Resend API key not set'}), 400

    trackings = models.get_email_tracking_for_contact(contact_id)
    if not trackings:
        return jsonify({'error': 'No original email'}), 400

    original = trackings[0]
    original_message_id = original.get('message_id', '') or original.get('resend_id', '')
    campaign = get_campaign_or_404(cid)

    subject = data.get('subject', '')
    body = data.get('body', '')
    first_name = contact['name'].split()[0] if contact.get('name') else ''
    from_email = settings.get('resend_from_email', '')
    rt_base = settings.get('reply_to_email', '')
    rt_user, rt_domain = rt_base.split('@')
    reply_to = f"{rt_user}+{contact_id}@{rt_domain}"
    sender_name = (campaign or {}).get('sender_name') or settings.get('sender_name', 'Your Name')
    signature = (campaign or {}).get('email_signature') or settings.get('email_signature', 'Best,\nYour Name')

    body_html = format_email_html(body, first_name, signature, settings.get('email_font', 'Georgia, serif'))

    try:
        result = send_threaded_followup(api_key, from_email, contact['email'],
            subject, body_html, original_message_id, reply_to=reply_to, sender_name=sender_name)

        thread_pos = len(trackings) + 1
        models.create_email_tracking({
            'contact_id': contact_id, 'user_id': session['user_id'], 'campaign_id': cid,
            'email_type': 'followup',
            'message_id': result.get('message_id', result.get('id', '')),
            'resend_id': result.get('id', ''), 'subject': subject, 'body': body,
            'thread_position': thread_pos
        })
        fu_count = models.get_followup_count(contact_id)
        models.create_followup({
            'contact_id': contact_id, 'user_id': session['user_id'], 'campaign_id': cid,
            'parent_email_id': original['id'], 'followup_number': fu_count + 1,
            'subject': subject, 'body': body
        })
        db = get_db()
        db.execute('UPDATE followups SET sent=1, sent_at=CURRENT_TIMESTAMP WHERE contact_id=? AND sent=0', (contact_id,))
        db.commit()
        db.close()
        return jsonify({'success': True, 'thread_position': thread_pos})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/c/<int:cid>/send/reply/<int:tracking_id>')
@login_required
def get_reply(cid, tracking_id):
    db = get_db()
    row = db.execute('SELECT et.*, c.name as contact_name, c.id as contact_id FROM email_tracking et JOIN contacts c ON et.contact_id=c.id WHERE et.id=?', (tracking_id,)).fetchone()
    db.close()
    return jsonify(dict(row)) if row else (jsonify({'error': 'Not found'}), 404)

# === Scheduling ===

@app.route('/c/<int:cid>/send/schedule', methods=['POST'])
@login_required
def schedule_emails(cid):
    """Schedule outreach emails for a specific date/time."""
    data = request.get_json()
    uid = session['user_id']
    scheduled_at = data.get('scheduled_at', '')  # ISO format: 2026-04-02T09:00
    if not scheduled_at:
        return jsonify({'error': 'No schedule time provided'}), 400

    contacts = models.get_contacts(uid, cid)
    ready = [c for c in contacts if c.get('email_approved') and not c.get('email_sent') and c.get('email')]
    if not ready:
        return jsonify({'error': 'No emails ready to send'}), 400

    contact_ids = [c['id'] for c in ready]
    job_id = models.create_scheduled_job(uid, cid, 'send_emails', scheduled_at,
        payload={'contact_ids': contact_ids})
    return jsonify({'success': True, 'job_id': job_id, 'count': len(contact_ids), 'scheduled_at': scheduled_at})

@app.route('/c/<int:cid>/send/schedule-followups', methods=['POST'])
@login_required
def schedule_followups(cid):
    """Schedule auto follow-ups for non-repliers."""
    data = request.get_json()
    uid = session['user_id']
    scheduled_at = data.get('scheduled_at', '')
    if not scheduled_at:
        return jsonify({'error': 'No schedule time provided'}), 400

    settings = models.get_all_settings(uid)
    delay = int(settings.get('followup_delay_days', '3'))
    max_fu = int(settings.get('max_followups', '3'))
    candidates = models.get_followup_candidates_for_auto(uid, cid, delay, max_fu)
    if not candidates:
        return jsonify({'error': 'No follow-up candidates right now'}), 400

    contact_ids = [c['contact_id'] for c in candidates]
    job_id = models.create_scheduled_job(uid, cid, 'send_followups', scheduled_at,
        payload={'contact_ids': contact_ids})
    return jsonify({'success': True, 'job_id': job_id, 'count': len(contact_ids), 'scheduled_at': scheduled_at})

@app.route('/c/<int:cid>/send/scheduled-jobs')
@login_required
def get_scheduled_jobs(cid):
    uid = session['user_id']
    jobs = models.get_scheduled_jobs(uid, cid)
    return jsonify({'jobs': jobs})

@app.route('/c/<int:cid>/send/scheduled-jobs/<int:job_id>', methods=['DELETE'])
@login_required
def cancel_scheduled_job(cid, job_id):
    models.delete_scheduled_job(job_id)
    return jsonify({'success': True})

# === Calendar ===

@app.route('/c/<int:cid>/calendar')
@login_required
def calendar_view(cid):
    campaign = get_campaign_or_404(cid)
    if not campaign:
        return redirect('/campaigns')
    uid = session['user_id']
    meetings = models.get_meetings(uid, cid)
    replied = models.get_replied_contacts(uid, cid)
    gcal_connected = bool(models.get_setting(uid, 'google_access_token'))
    return render_template('calendar.html', campaign=campaign, meetings=meetings,
        replied_contacts=replied, gcal_connected=gcal_connected, active_page='calendar')

@app.route('/calendar/auth')
@login_required
def calendar_auth():
    settings = models.get_all_settings(session['user_id'])
    client_id = settings.get('google_client_id', '')
    if not client_id:
        flash('Set Google Client ID in Settings first', 'error')
        return redirect('/settings')
    redirect_uri = request.url_root.rstrip('/') + url_for('calendar_callback')
    return redirect(get_auth_url(client_id, redirect_uri))

@app.route('/calendar/callback')
@login_required
def calendar_callback():
    code = request.args.get('code')
    if not code:
        flash('Authorization failed', 'error')
        return redirect('/campaigns')
    uid = session['user_id']
    settings = models.get_all_settings(uid)
    redirect_uri = request.url_root.rstrip('/') + url_for('calendar_callback')
    try:
        creds = handle_callback(code, settings.get('google_client_id', ''), settings.get('google_client_secret', ''), redirect_uri)
        models.set_setting(uid, 'google_access_token', creds['access_token'])
        models.set_setting(uid, 'google_refresh_token', creds.get('refresh_token', ''))
        flash('Google Calendar connected!', 'success')
    except Exception as e:
        flash(f'Failed: {e}', 'error')
    return redirect('/campaigns')

@app.route('/calendar/slots')
@login_required
def calendar_slots():
    date = request.args.get('date')
    if not date:
        return jsonify({'slots': []})
    uid = session['user_id']
    settings = models.get_all_settings(uid)
    access_token = settings.get('google_access_token', '')
    if not access_token:
        return jsonify({'error': 'Not connected'}), 400
    try:
        return jsonify({'slots': get_free_slots(access_token, date)})
    except Exception:
        try:
            new_token = refresh_token(settings.get('google_client_id',''), settings.get('google_client_secret',''), settings.get('google_refresh_token',''))
            models.set_setting(uid, 'google_access_token', new_token)
            return jsonify({'slots': get_free_slots(new_token, date)})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@app.route('/c/<int:cid>/calendar/schedule', methods=['POST'])
@login_required
def schedule_meeting(cid):
    data = request.get_json()
    uid = session['user_id']
    settings = models.get_all_settings(uid)
    access_token = settings.get('google_access_token', '')
    if not access_token:
        return jsonify({'error': 'Not connected'}), 400
    contact = models.get_contact(int(data.get('contact_id', 0)))
    if not contact:
        return jsonify({'error': 'Not found'}), 404
    title = data.get('title', f"Intro Call — {contact['name'].split()[0]}")
    datetime_str = f"{data.get('date','')}T{data.get('time','')}:00"
    duration = int(data.get('duration', 30))
    try:
        result = gcal_create_meeting(access_token, title, datetime_str, duration, contact['email'], add_meet=data.get('add_meet', True))
        models.create_meeting({
            'contact_id': contact['id'], 'user_id': uid, 'campaign_id': cid,
            'title': title, 'datetime': datetime_str, 'duration_minutes': duration,
            'google_event_id': result.get('event_id',''), 'meet_link': result.get('meet_link',''), 'status': 'scheduled'
        })
        return jsonify({'success': True, 'meet_link': result.get('meet_link','')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# === Settings (global) ===

@app.route('/settings')
@login_required
def settings_page():
    s = models.get_all_settings(session['user_id'])
    return render_template('settings.html', s=s, campaign=None, active_page='settings')

@app.route('/settings/save', methods=['POST'])
@login_required
def save_settings():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data'}), 400
        models.set_settings_bulk(session['user_id'], data)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================
#  MAIN
# ============================================================

def execute_scheduled_job(job):
    """Execute a single scheduled job."""
    uid = job['user_id']
    cid = job['campaign_id']
    payload = json.loads(job.get('payload', '{}'))
    settings = models.get_all_settings(uid)
    api_key = settings.get('resend_api_key', '')
    if not api_key:
        models.update_scheduled_job(job['id'], {'status': 'failed', 'result': 'No API key', 'executed_at': datetime.now().isoformat()})
        return

    from_email = settings.get('resend_from_email', '')
    reply_to_base = settings.get('reply_to_email', '')
    campaign = models.get_campaign(cid)
    sender_name = (campaign or {}).get('sender_name') or settings.get('sender_name', 'Your Name')
    signature = (campaign or {}).get('email_signature') or settings.get('email_signature', 'Best,\nYour Name')
    font = settings.get('email_font', 'Georgia, serif')

    if job['job_type'] == 'send_emails':
        contact_ids = payload.get('contact_ids', [])
        sent, failed = 0, 0
        for contact_id in contact_ids:
            c = models.get_contact(contact_id)
            if not c or c.get('email_sent') or not c.get('email'):
                continue
            try:
                subject = c.get('email_subject', '')
                body = c.get('email_body', '')
                first_name = c['name'].split()[0] if c.get('name') else ''
                body_html = format_email_html(body, first_name, signature, font)
                rt_user, rt_domain = reply_to_base.split('@')
                reply_to = f"{rt_user}+{c['id']}@{rt_domain}"
                result = send_email(api_key, from_email, c['email'], subject, body_html,
                                   reply_to=reply_to, sender_name=sender_name)
                models.create_email_tracking({
                    'contact_id': c['id'], 'user_id': uid, 'campaign_id': cid,
                    'email_type': 'outreach',
                    'message_id': result.get('message_id', result.get('id', '')),
                    'resend_id': result.get('id', ''),
                    'subject': subject, 'body': body, 'thread_position': 1
                })
                models.update_contact(c['id'], {'email_sent': 1})
                sent += 1
                time.sleep(0.5)
            except Exception:
                failed += 1
        models.update_scheduled_job(job['id'], {
            'status': 'completed', 'executed_at': datetime.now().isoformat(),
            'result': json.dumps({'sent': sent, 'failed': failed})
        })

    elif job['job_type'] == 'send_followups':
        contact_ids = payload.get('contact_ids', [])
        claude_key = settings.get('claude_api_key', '')
        claude_model = settings.get('claude_model', '')
        sent, failed = 0, 0
        for contact_id in contact_ids:
            contact = models.get_contact(contact_id)
            if not contact or not contact.get('email'):
                continue
            trackings = models.get_email_tracking_for_contact(contact_id)
            if not trackings:
                continue
            # Skip if replied since job was created
            latest = trackings[-1]
            if latest.get('replied_at'):
                continue
            original = trackings[0]
            original_message_id = original.get('message_id', '') or original.get('resend_id', '')
            fu_count = models.get_followup_count(contact_id)
            try:
                fu = generate_followup(contact, original, fu_count + 1, claude_key, claude_model,
                    custom_prompt=(campaign or {}).get('followup_prompt', ''))
                first_name = contact['name'].split()[0] if contact.get('name') else ''
                body_html = format_email_html(fu['body'], first_name, signature, font)
                rt_user, rt_domain = reply_to_base.split('@')
                reply_to = f"{rt_user}+{contact_id}@{rt_domain}"
                result = send_threaded_followup(api_key, from_email, contact['email'],
                    fu['subject'], body_html, original_message_id, reply_to=reply_to, sender_name=sender_name)
                thread_pos = len(trackings) + 1
                models.create_email_tracking({
                    'contact_id': contact_id, 'user_id': uid, 'campaign_id': cid,
                    'email_type': 'followup',
                    'message_id': result.get('message_id', result.get('id', '')),
                    'resend_id': result.get('id', ''),
                    'subject': fu['subject'], 'body': fu['body'], 'thread_position': thread_pos
                })
                models.create_followup({
                    'contact_id': contact_id, 'user_id': uid, 'campaign_id': cid,
                    'parent_email_id': original['id'], 'followup_number': fu_count + 1,
                    'subject': fu['subject'], 'body': fu['body']
                })
                db = get_db()
                db.execute('UPDATE followups SET sent=1, sent_at=CURRENT_TIMESTAMP WHERE contact_id=? AND sent=0', (contact_id,))
                db.commit()
                db.close()
                sent += 1
                time.sleep(1)
            except Exception:
                failed += 1
        models.update_scheduled_job(job['id'], {
            'status': 'completed', 'executed_at': datetime.now().isoformat(),
            'result': json.dumps({'sent': sent, 'failed': failed})
        })

def start_background_tracker():
    def tracker_loop():
        while True:
            time.sleep(30)
            try:
                # Execute pending scheduled jobs
                now_str = datetime.now().strftime('%Y-%m-%dT%H:%M')
                pending = models.get_pending_jobs(now_str)
                for job in pending:
                    models.update_scheduled_job(job['id'], {'status': 'running'})
                    try:
                        execute_scheduled_job(job)
                    except Exception as e:
                        models.update_scheduled_job(job['id'], {
                            'status': 'failed', 'executed_at': datetime.now().isoformat(),
                            'result': str(e)
                        })
            except Exception:
                pass
            try:
                # Tracking polling (every 5 min worth of 30s loops = every ~5 min)
                db = get_db()
                users = db.execute('SELECT id FROM users').fetchall()
                db.close()
                for u in users:
                    uid = u['id']
                    settings = models.get_all_settings(uid)
                    api_key = settings.get('resend_api_key', '')
                    if api_key:
                        poll_resend_status(api_key, uid)
                    imap_host = settings.get('imap_host', '')
                    imap_email = settings.get('imap_email', '')
                    imap_password = settings.get('imap_password', '')
                    if imap_host and imap_email and imap_password:
                        check_imap_replies(imap_host, imap_email, imap_password, uid, int(settings.get('imap_port', '993')))
            except Exception:
                pass
    threading.Thread(target=tracker_loop, daemon=True).start()

if __name__ == '__main__':
    init_db()
    start_background_tracker()
    print('\n  Omega Outreach Engine')
    print('  http://localhost:5000')
    print('  Background: scheduler (30s) + tracker\n')
    app.run(debug=True, port=5000, use_reloader=False)
