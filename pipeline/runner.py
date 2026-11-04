from . import dedup, enrichment, linkedin, persona, segmentation, email_finder, outreach

STAGE_ORDER = ['dedup', 'enrichment', 'linkedin', 'persona', 'segmentation', 'email_finder', 'outreach']

SKIP_CHECKS = {
    'enrichment': enrichment.should_skip_enrichment,
    'linkedin': linkedin.should_skip_linkedin,
    'persona': persona.should_skip_persona,
    'segmentation': segmentation.should_skip_segmentation,
    'email_finder': email_finder.should_skip_email,
    'outreach': outreach.should_skip_outreach,
}

def run_pipeline(contacts, stages_config, settings, campaign=None, log_callback=None):
    def log(cid, name, stage, status, msg):
        if log_callback:
            log_callback(cid, name, stage, status, msg)

    summary = {s: {'total': 0, 'done': 0, 'skipped': 0, 'errors': 0} for s in STAGE_ORDER}

    # Extract campaign prompts
    camp_enrichment_prompt = (campaign or {}).get('enrichment_prompt', '') or ''
    camp_persona_prompt = (campaign or {}).get('persona_prompt', '') or ''
    camp_outreach_prompt = (campaign or {}).get('outreach_prompt', '') or ''
    camp_soft_cta = (campaign or {}).get('soft_cta', '') or ''
    camp_banned = (campaign or {}).get('banned_phrases', '') or ''
    camp_followup_prompt = (campaign or {}).get('followup_prompt', '') or ''

    # Stage 1: Dedup
    dedup_mode = stages_config.get('dedup', 'skip')
    if dedup_mode in ('always', 'all'):
        contacts, removed = dedup.deduplicate(contacts)
        for r in removed:
            log(r['contact'].get('id', 0), r['contact'].get('name', ''), 'dedup', 'removed', r['reason'])
        summary['dedup']['done'] = len(contacts)
        summary['dedup']['skipped'] = len(removed)
        log(0, '', 'dedup', 'success', f'{len(contacts)} unique, {len(removed)} duplicates removed')
    else:
        log(0, '', 'dedup', 'skipped', 'Deduplication skipped')

    # Stages 2-7: Per-contact
    for contact in contacts:
        cid = contact.get('id', 0)
        cname = contact.get('name', '')

        for stage in STAGE_ORDER[1:]:
            mode = stages_config.get(stage, 'skip')
            if mode == 'skip':
                summary[stage]['skipped'] += 1
                continue

            summary[stage]['total'] += 1

            if mode == 'missing_only' and stage in SKIP_CHECKS:
                if SKIP_CHECKS[stage](contact):
                    summary[stage]['skipped'] += 1
                    log(cid, cname, stage, 'skipped', 'Data already exists')
                    continue

            try:
                if stage == 'enrichment':
                    result = enrichment.enrich_contact(
                        contact, settings.get('ollama_url'), settings.get('ollama_model'),
                        custom_prompt=camp_enrichment_prompt if camp_enrichment_prompt else None)
                    contact.update(result)
                    log(cid, cname, stage, 'success', f"Seniority: {result.get('seniority_level')}, Relevance: {result.get('relevance_score')}")

                elif stage == 'linkedin':
                    result = linkedin.find_linkedin(contact, settings.get('brave_api_key'))
                    contact.update(result)
                    log(cid, cname, stage, 'success', f"Status: {result.get('linkedin_status')}")

                elif stage == 'persona':
                    result = persona.generate_persona(
                        contact, settings.get('claude_api_key'), settings.get('claude_model'),
                        custom_prompt=camp_persona_prompt if camp_persona_prompt else None)
                    contact.update(result)
                    log(cid, cname, stage, 'success', f"Confidence: {result.get('persona_confidence')}")

                elif stage == 'segmentation':
                    t1 = int(settings.get('tier1_threshold', 70))
                    t2 = int(settings.get('tier2_threshold', 40))
                    result = segmentation.segment_contact(contact, t1, t2)
                    contact.update(result)
                    log(cid, cname, stage, 'success', f"{result.get('tier')} (Score: {result.get('tier_score')})")

                elif stage == 'email_finder':
                    result = email_finder.find_email(
                        contact, settings.get('brave_api_key'),
                        settings.get('snov_client_id'), settings.get('snov_client_secret'))
                    contact.update(result)
                    log(cid, cname, stage, 'success', f"{result.get('email_status')}: {result.get('email', 'none')}")

                elif stage == 'outreach':
                    result = outreach.generate_outreach(
                        contact, settings.get('claude_api_key'), settings.get('claude_model'),
                        settings.get('ollama_url'), settings.get('ollama_model'),
                        custom_prompt=camp_outreach_prompt if camp_outreach_prompt else None,
                        soft_cta=camp_soft_cta, banned_phrases=camp_banned)
                    contact.update(result)
                    log(cid, cname, stage, 'success', f"Subject: {result.get('email_subject', '')[:50]}")

                summary[stage]['done'] += 1

            except Exception as e:
                summary[stage]['errors'] += 1
                log(cid, cname, stage, 'error', str(e))

    return contacts, summary
