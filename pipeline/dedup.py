import re

THRESHOLD = 85

def normalize(s):
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"^(hon'ble\s+minister\s+shri\s+|hon'ble\s+|shri\s+|smt\.?\s+|dr\.?\s+|mr\.?\s+|mrs\.?\s+|ms\.?\s+|prof\.?\s+)", "", s, flags=re.I)
    s = re.sub(r"\s+(jr\.?|sr\.?|phd|mba)$", "", s, flags=re.I)
    s = re.sub(r"\s*(pvt\.?|private|ltd\.?|limited|inc\.?|technologies|tech)\s*", " ", s, flags=re.I)
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def levenshtein(a, b):
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            if a[i-1] == b[j-1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j-1])
            prev = temp
    return dp[n]

def similarity(a, b):
    if not a or not b:
        return 0
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 100
    return ((max_len - levenshtein(a, b)) / max_len) * 100

def deduplicate(contacts):
    seen = []
    unique = []
    removed = []
    for c in contacts:
        norm_name = normalize(c.get('name', ''))
        norm_company = normalize(c.get('company', ''))
        key = f"{norm_name} @ {norm_company}"
        is_dup = False
        for existing in seen:
            sim = similarity(key, existing['key'])
            if sim >= THRESHOLD:
                is_dup = True
                removed.append({
                    'contact': c,
                    'reason': f'Matched "{existing["name"]} @ {existing["company"]}" ({sim:.1f}%)'
                })
                break
        if not is_dup:
            seen.append({'key': key, 'name': c.get('name', ''), 'company': c.get('company', '')})
            unique.append(c)
    return unique, removed
