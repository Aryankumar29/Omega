# Omega

AI-powered B2B sales outreach automation platform. Automates the full workflow from contact enrichment to personalized email campaigns, tracking, follow-ups, and meeting scheduling.

## What It Does

Omega takes raw contact lists (e.g., event attendees) and runs them through a 7-stage AI pipeline:

1. **Deduplication** - Fuzzy matching (Levenshtein distance, 85% threshold) to remove duplicate contacts
2. **Enrichment** - Local LLM (Ollama/Llama 3.1:8b) infers seniority, industry, company size, relevance, and pain points
3. **LinkedIn Lookup** - Brave Search API finds LinkedIn profile URLs with confidence scoring
4. **Persona Generation** - Claude API builds detailed buyer personas with goals, objections, and personalization hooks
5. **Segmentation** - Scores contacts 0-100 and assigns tiers:
   - **Tier 1** (70+): High-value leads - founder-routed, multi-channel outreach
   - **Tier 2** (40-69): Mid-value - email sequence + LinkedIn
   - **Tier 3** (<40): Lower priority - post-event email only
6. **Email Finding** - 3-layer discovery: Snov.io (Tier 1) -> Brave Search (Tier 1+2) -> Domain construction (all)
7. **Outreach Generation** - Claude (Tier 1+2) or Ollama (Tier 3) writes personalized email + LinkedIn message

After pipeline completion, review/approve emails and send via Resend with full delivery tracking, automated follow-ups, and Google Calendar integration for meeting scheduling.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Flask (Python) |
| Database | SQLite (WAL mode) |
| Frontend | Jinja2 templates, vanilla JS, custom CSS |
| AI - Local | Ollama (Llama 3.1:8b) |
| AI - Cloud | Claude API (Anthropic) |
| Search | Brave Search API |
| Email Sending | Resend API |
| Email Verification | Snov.io API |
| Reply Detection | IMAP (Gmail/custom) |
| Calendar | Google Calendar API (OAuth 2.0) |

## Features

- **Campaign Management** - Create event, cold, nurture, or custom campaigns with configurable prompts, CTAs, and banned phrases
- **Bulk Contact Import** - Upload CSV/Excel files with column mapping preview
- **Real-time Pipeline** - Run stages independently or as a batch; live progress via SSE polling
- **Email Review UI** - Card-based email approval with keyboard navigation (arrow keys), inline editing, and regeneration
- **Threaded Follow-ups** - Auto-generate up to 3 follow-ups per contact (gentle nudge -> value add -> breakup email) with proper email threading headers
- **Delivery Tracking** - Tracks delivered, opened (with count), clicked, bounced, and replied status via Resend + IMAP
- **Meeting Scheduling** - Google Calendar free/busy slot detection, Google Meet link generation, calendar invites
- **Scheduled Jobs** - Schedule email sends and follow-ups for specific dates/times
- **Attachments** - Upload files (max 10MB) to include in campaign emails
- **Per-contact Pipeline** - Run any single stage on individual contacts
- **Contact Export** - Export enriched contacts to CSV
- **Multi-user Auth** - User registration with salted password hashing (Werkzeug)

## Setup

### Prerequisites

- Python 3.8+
- [Ollama](https://ollama.ai) with `llama3.1:8b` model pulled and running
- API keys: Claude (Anthropic), Brave Search, Resend (required); Snov.io, Google OAuth (optional)

### Installation

```bash
git clone https://github.com/Aryankumar29/Omega.git
cd Omega
python -m venv venv
source venv/Scripts/activate  # Windows (Git Bash)
# source venv/bin/activate    # Linux/Mac
pip install -r requirements.txt
```

### Run

```bash
python app.py
```

The app starts at `http://127.0.0.1:5000`.

### First-time Configuration

1. Register a user account at `/register`
2. Go to **Settings** and add your API keys:
   - `claude_api_key` - Anthropic API key
   - `brave_api_key` - Brave Search API key
   - `resend_api_key` - Resend API key
   - `snov_client_id` / `snov_client_secret` - Snov.io credentials (optional, Tier 1 email finding)
   - `google_client_id` / `google_client_secret` - Google OAuth (optional, calendar integration)
   - IMAP settings for reply detection (optional)
3. Make sure Ollama is running with the model: `ollama run llama3.1:8b`

## Project Structure

```
Omega/
├── app.py                  # Flask app, all routes & API endpoints
├── config.py               # Default settings & campaign prompt templates
├── database.py             # SQLite connection & schema initialization
├── models.py               # Database query functions (CRUD)
├── pipeline/
│   ├── runner.py           # Pipeline orchestrator (batch & single runs)
│   ├── dedup.py            # Fuzzy deduplication
│   ├── enrichment.py       # Ollama-based contact enrichment
│   ├── linkedin.py         # LinkedIn profile lookup via Brave
│   ├── persona.py          # Claude-based persona generation
│   ├── segmentation.py     # Tier scoring & assignment
│   ├── email_finder.py     # 3-layer email discovery
│   └── outreach.py         # AI email/LinkedIn copy generation
├── email_service/
│   ├── resend_client.py    # Resend API email sending & formatting
│   ├── tracking.py         # Delivery status polling & IMAP reply detection
│   └── followup.py         # AI follow-up email generation
├── calendar_service/
│   └── google_cal.py       # Google Calendar OAuth, free slots, meeting creation
├── templates/              # Jinja2 HTML templates
│   ├── base.html           # Layout with sidebar navigation
│   ├── dashboard.html      # Campaign overview & stats
│   ├── pipeline.html       # Pipeline stage config & live logs
│   ├── contacts.html       # Contact list, search, upload/export
│   ├── email_review.html   # Email approval workflow
│   ├── send_track.html     # Send emails & tracking dashboard
│   ├── calendar.html       # Meeting scheduling
│   ├── campaign_edit.html  # Campaign settings & prompts
│   └── settings.html       # API keys & email config
├── static/
│   ├── css/style.css       # Custom design system (orange accent, dark sidebar)
│   └── js/app.js           # Frontend logic (inline edit, SSE, modals, toasts)
├── requirements.txt
└── run.bat                 # Windows batch launcher
```

## Workflow

```
CSV Upload → Dedup → Enrich (Ollama) → LinkedIn (Brave) → Persona (Claude)
    → Segment & Score → Find Emails (Snov/Brave/Construct)
    → Generate Outreach (Claude/Ollama) → Review & Approve
    → Send via Resend → Track Opens/Clicks/Replies (Resend + IMAP)
    → Auto Follow-ups (Claude) → Schedule Meetings (Google Calendar)
```

## API Endpoints

### Campaigns
- `POST /campaigns/create` - Create campaign
- `GET /c/<id>/` - Campaign dashboard
- `PUT /c/<id>/update` - Update campaign settings
- `DELETE /c/<id>/delete` - Delete campaign

### Contacts
- `POST /c/<id>/contacts/upload` - Bulk upload (CSV/Excel)
- `POST /c/<id>/contacts/add` - Add single contact
- `GET /c/<id>/contacts/export` - Export to CSV

### Pipeline
- `POST /c/<id>/pipeline/run` - Start pipeline batch run
- `GET /c/<id>/pipeline/status/<run_id>` - Poll progress
- `POST /c/<id>/pipeline/run-single/<contact_id>/<stage>` - Run single stage

### Email
- `POST /c/<id>/send/emails` - Send approved emails (SSE stream)
- `POST /c/<id>/send/test` - Send test email
- `POST /c/<id>/send/followup/<contact_id>` - Send follow-up
- `POST /c/<id>/send/schedule` - Schedule emails
- `GET /send/tracking-updates` - Poll tracking status

### Calendar
- `GET /calendar/auth` - Google OAuth flow
- `GET /calendar/slots?date=YYYY-MM-DD` - Get free slots
- `POST /c/<id>/calendar/schedule` - Create meeting

## License

All rights reserved.
