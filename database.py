import sqlite3
import config

def get_db():
    db = sqlite3.connect(config.DATABASE, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db

def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            campaign_type TEXT DEFAULT 'event',
            status TEXT DEFAULT 'active',
            enrichment_prompt TEXT DEFAULT '',
            persona_prompt TEXT DEFAULT '',
            outreach_prompt TEXT DEFAULT '',
            followup_prompt TEXT DEFAULT '',
            soft_cta TEXT DEFAULT '',
            banned_phrases TEXT DEFAULT '',
            email_signature TEXT DEFAULT '',
            sender_name TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            campaign_id INTEGER,
            name TEXT NOT NULL,
            designation TEXT DEFAULT '',
            company TEXT DEFAULT '',
            profile_url TEXT DEFAULT '',
            image_url TEXT DEFAULT '',
            source_url TEXT DEFAULT '',
            scraped_at TEXT DEFAULT '',
            seniority_level TEXT DEFAULT '',
            industry_vertical TEXT DEFAULT '',
            company_size_estimate TEXT DEFAULT '',
            relevance_score TEXT DEFAULT '',
            relevance_reasoning TEXT DEFAULT '',
            inferred_pain_points TEXT DEFAULT '',
            enrichment_confidence TEXT DEFAULT '',
            linkedin_url TEXT DEFAULT '',
            linkedin_status TEXT DEFAULT '',
            persona TEXT DEFAULT '',
            context_summary TEXT DEFAULT '',
            personalization_themes TEXT DEFAULT '',
            recommended_tone TEXT DEFAULT '',
            persona_confidence TEXT DEFAULT '',
            tier TEXT DEFAULT '',
            tier_score INTEGER DEFAULT 0,
            assigned_to TEXT DEFAULT '',
            channels TEXT DEFAULT '',
            routing_notes TEXT DEFAULT '',
            downgrade_reason TEXT DEFAULT '',
            email TEXT DEFAULT '',
            email_confidence INTEGER DEFAULT 0,
            email_status TEXT DEFAULT '',
            email_source TEXT DEFAULT '',
            personal_email TEXT DEFAULT '',
            email_subject TEXT DEFAULT '',
            email_body TEXT DEFAULT '',
            linkedin_message TEXT DEFAULT '',
            email_approved INTEGER DEFAULT 0,
            email_sent INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        );

        CREATE TABLE IF NOT EXISTS email_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            campaign_id INTEGER,
            email_type TEXT NOT NULL,
            message_id TEXT DEFAULT '',
            resend_id TEXT DEFAULT '',
            subject TEXT DEFAULT '',
            body TEXT DEFAULT '',
            sent_at TIMESTAMP,
            delivered_at TIMESTAMP,
            opened_at TIMESTAMP,
            open_count INTEGER DEFAULT 0,
            clicked_at TIMESTAMP,
            bounced_at TIMESTAMP,
            replied_at TIMESTAMP,
            reply_content TEXT DEFAULT '',
            thread_position INTEGER DEFAULT 1,
            status TEXT DEFAULT 'sent',
            FOREIGN KEY (contact_id) REFERENCES contacts(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        );

        CREATE TABLE IF NOT EXISTS followups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            campaign_id INTEGER,
            parent_email_id INTEGER,
            followup_number INTEGER DEFAULT 1,
            subject TEXT DEFAULT '',
            body TEXT DEFAULT '',
            approved INTEGER DEFAULT 0,
            sent INTEGER DEFAULT 0,
            message_id TEXT DEFAULT '',
            sent_at TIMESTAMP,
            FOREIGN KEY (contact_id) REFERENCES contacts(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
            FOREIGN KEY (parent_email_id) REFERENCES email_tracking(id)
        );

        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value TEXT DEFAULT '',
            UNIQUE(user_id, key),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            campaign_id INTEGER,
            title TEXT DEFAULT '',
            datetime TEXT DEFAULT '',
            duration_minutes INTEGER DEFAULT 30,
            google_event_id TEXT DEFAULT '',
            meet_link TEXT DEFAULT '',
            status TEXT DEFAULT 'scheduled',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contact_id) REFERENCES contacts(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        );

        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            campaign_id INTEGER,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            total_contacts INTEGER DEFAULT 0,
            stages_config TEXT DEFAULT '{}',
            status TEXT DEFAULT 'running',
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        );

        CREATE TABLE IF NOT EXISTS scheduled_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            campaign_id INTEGER,
            job_type TEXT NOT NULL,
            scheduled_at TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            payload TEXT DEFAULT '{}',
            result TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            executed_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        );

        CREATE TABLE IF NOT EXISTS pipeline_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            contact_id INTEGER,
            contact_name TEXT DEFAULT '',
            stage TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (run_id) REFERENCES pipeline_runs(id)
        );
    ''')
    db.commit()
    db.close()
