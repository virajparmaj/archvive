"""Offline audit of the clarified US/2020–2025 scope; preserves canonical evidence."""
import json
import re
from collections import Counter
from pathlib import Path

from comparison import us_eligible

DATA = Path(__file__).resolve().parents[1] / 'data/capital-one'
PATTERNS = {
    'ml_ai': r'\bmachine learning\b|\bartificial intelligence\b|\bAI\b|\bML\b',
    'risk': r'\brisk\b',
    'fraud': r'\bfraud\b',
    'credit': r'\bcredit\b',
    'business_analyst': r'\bbusiness analyst\b|\bbusiness analysis\b',
    'product_management': r'\bproduct manag(?:er|ement)\b',
    'data_scientist': r'\bdata scien(?:tist|ce)\b',
}


def tags(title: str) -> list[str]:
    # A department/domain mention does not make a lawyer or designer an ML/risk role.
    if re.search(r'general counsel|\blawyer\b|\bdesigner\b', title, re.I):
        return []
    return [key for key, pattern in PATTERNS.items() if re.search(pattern, title, re.I)]


def compact(row: dict) -> tuple[str, list[dict]]:
    """Conservative line filtering; record every removal for reversible inspection."""
    kept, removed = [], []
    footer = False
    for line in row['description'].splitlines():
        reason = None
        if re.match(r'No agencies please|Capital One is an Equal Opportunity Employer', line, re.I):
            footer = True
        if footer:
            reason = 'standard legal/recruiting footer'
        elif line.strip() == row['title'].strip():
            reason = 'title retained in metadata'
        elif re.search(r'United States of America|^United States-', line) and len(line) < 180:
            reason = 'location retained in metadata'
        elif re.match(r'^At Capital One, we(?:’|\x27)re on a mission to change banking for good', line):
            reason = 'standard company introduction'
        elif re.fullmatch(r'\s*(?:https?://\S+|View (?:location|map)|Apply(?: now)?|Save job|Share job)\s*', line, re.I):
            reason = 'standalone navigation or URL'
        if reason:
            removed.append({'text': line, 'reason': reason})
        else:
            kept.append(line)
    return '\n'.join(kept).strip(), removed


def main() -> None:
    rows = json.loads((DATA / 'results.json').read_text())
    availability = {r['original_url']: r for r in json.loads((DATA / 'modern-original-availability.json').read_text())}
    historical = [r for r in rows if r['historical']]
    window = [r for r in historical if r.get('archive_timestamp_verified') and
              '2020' <= (r.get('archive_capture_at') or '')[:4] <= '2025']
    us = [r for r in window if us_eligible(r)]
    selected, removals, uncertain = [], {}, []
    for r in window:
        role_tags = tags(r['title'])
        if not role_tags:
            continue
        if not us_eligible(r):
            uncertain.append({'version_key': r['version_key'], 'title': r['title'],
                              'location': r['location'], 'reason': 'US evidence absent or non-US location'})
            continue
        text, removed = compact(r)
        av = availability.get(r['original_url'])
        item = {k: r.get(k) for k in ('version_key', 'posting_key', 'title', 'identifiers',
                'location', 'archive_capture_at', 'source_declared_dates', 'review_status')}
        item.update(role_tags=role_tags, comparison_text=text,
                    original_unavailability=av, deletion_date_within_2020_2025='not established',
                    evidence_reference={'version_key': r['version_key'], 'file': 'historical-results.json'},
                    original_characters=len(r['description']), compact_characters=len(text))
        selected.append(item)
        removals[r['version_key']] = removed
    panel = json.loads((DATA / 'comparison-results.json').read_text())
    target_keys = {r['version_key'] for r in selected}
    summary = {
        'method': 'Conservative title matches; overlapping tags; US positive evidence; verified capture year, not deletion year. No seniority or graduate exclusion.',
        'historical_versions': len(historical), 'verified_window_versions': len(window),
        'us_window_versions': len(us), 'target_versions': len(selected),
        'target_posting_groups': len({r['posting_key'] for r in selected}),
        'target_original_404_versions': sum(bool(r['original_unavailability'] and r['original_unavailability']['status'] == 404) for r in selected),
        'validated_target_versions': sum(r['review_status'] == 'validated' for r in selected),
        'proven_deletion_date_in_window': 0,
        'target_by_year': dict(sorted(Counter(r['archive_capture_at'][:4] for r in selected).items())),
        'target_tags_overlapping': dict(Counter(t for r in selected for t in r['role_tags'])),
        'old_panel_target_versions': sum(r['version_key'] in target_keys for r in panel),
        'old_panel_total': len(panel), 'excluded_or_location_unresolved_target_titles': len(uncertain),
        'original_description_characters': sum(r['original_characters'] for r in selected),
        'compact_description_characters': sum(r['compact_characters'] for r in selected),
        'tokens_note': 'Character reduction only; token savings depend on tokenizer. Role-specific introductions retained.',
        'current_versions_outside_historical_target': sum(not r['historical'] for r in rows),
    }
    for name, value in [('objective-audit', summary), ('target-comparison-compact', selected),
                        ('target-comparison-removals', removals), ('target-location-review', uncertain)]:
        (DATA / f'{name}.json').write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
