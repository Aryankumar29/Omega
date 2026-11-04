def should_skip_segmentation(contact):
    return bool(contact.get('tier') and contact.get('tier_score'))

def segment_contact(contact, tier1_threshold=70, tier2_threshold=40):
    seniority = (contact.get('seniority_level') or 'Unknown').lower()
    size_str = (contact.get('company_size_estimate') or 'Unknown').lower()
    confidence = (contact.get('enrichment_confidence') or 'low').lower()
    persona_conf = (contact.get('persona_confidence') or 'low').lower()
    pain = (contact.get('inferred_pain_points') or '').lower()
    industry = (contact.get('industry_vertical') or '').lower()
    relevance_score = (contact.get('relevance_score') or 'low').lower()
    persona_text = (contact.get('persona') or '').lower()
    context = (contact.get('context_summary') or '').lower()

    score = 0

    # 1. Seniority (max 35)
    if any(x in seniority for x in ['c-suite', 'ceo', 'cfo', 'cto', 'founder', 'chairman', 'co-founder']):
        score += 35
    elif any(x in seniority for x in ['vp', 'president']):
        score += 25
    elif any(x in seniority for x in ['director', 'general manager']):
        score += 15
    elif any(x in seniority for x in ['manager', 'head', 'lead']):
        score += 8
    else:
        score += 2

    # 2. Company Size (max 30)
    if 'enterprise' in size_str or '1000+' in size_str:
        score += 30
    elif 'mid-market' in size_str or '100-1000' in size_str:
        score += 18
    elif 'startup' in size_str or '<100' in size_str:
        score += 8
    else:
        score += 5

    # 3. Confidence (max 20)
    conf_score = 0
    if confidence == 'high': conf_score += 10
    elif confidence == 'medium': conf_score += 5
    if persona_conf == 'high': conf_score += 10
    elif persona_conf == 'medium': conf_score += 5
    score += conf_score

    # 4. Relevance (max 15)
    relevance = 0
    if relevance_score == 'high': relevance = 10
    elif relevance_score == 'medium': relevance = 5
    keywords = ['pricing', 'benchmark', 'competitor', 'assortment', 'data automation',
        'analytics', 'dynamic pricing', 'competitive intelligence', 'price optimization',
        'market intelligence', 'price monitoring', 'retail analytics', 'e-commerce analytics']
    search_text = f'{pain} {persona_text} {context} {industry}'
    for kw in keywords:
        if kw in search_text:
            relevance = 15
            break
    score += relevance

    # Tier mapping
    tier = 'Tier 3'
    if score >= tier1_threshold: tier = 'Tier 1'
    elif score >= tier2_threshold: tier = 'Tier 2'

    downgrade_reason = 'None'
    if tier == 'Tier 1' and (confidence == 'low' or persona_conf == 'low'):
        tier = 'Tier 2'
        downgrade_reason = 'Downgraded — low confidence'

    if tier == 'Tier 1':
        assigned_to = 'Founder'
        channels = 'LinkedIn Personal + Email + Manual review'
    elif tier == 'Tier 2':
        assigned_to = 'AE'
        channels = 'Email Sequence + LinkedIn Connection'
    else:
        assigned_to = 'SDR'
        channels = 'Post-event Email only'

    routing_notes = f'Score: {score}/100 | {seniority} | {size_str} | E={confidence},P={persona_conf} | Rel={relevance}/15'

    return {
        'tier': tier,
        'tier_score': score,
        'assigned_to': assigned_to,
        'channels': channels,
        'routing_notes': routing_notes,
        'downgrade_reason': downgrade_reason
    }
