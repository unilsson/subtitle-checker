"""Conservative release-name comparisons. Never claims subtitle timing is verified."""
from __future__ import annotations
import re

COMMON = {'x264', 'x265', 'h264', 'h265', 'hevc', 'avc', 'aac', 'ac3', 'dts',
          'ddp', 'dd', 'atmos', '10bit', '8bit', 'proper', 'repack', 'remux',
          'multi', 'internal', 'limited', 'en', 'eng', 'sv', 'swe', 'srt',
          'mkv', 'mp4', 'avi', 'sub', 'subtitle', 'subtitles'}
SOURCES = {
    'bluray': ('bluray', 'blu ray', 'bdrip', 'brrip', 'bdremux', 'bdr'),
    'webdl': ('web dl', 'webdl', 'web-dl', 'web.dl'),
    'webrip': ('web rip', 'webrip', 'web-rip', 'web.rip'),
    'hdtv': ('hdtv', 'pdtv'),
    'dvdrip': ('dvdrip', 'dvd rip', 'dvdr'),
}
EDITION = {'extended', 'uncut', 'unrated', 'directors', 'theatrical', 'imax', 'criterion'}


def compact(title: str) -> str:
    """Keep alphanumeric characters only for strict full release-name matching."""
    title = re.sub(r'\.(mkv|avi|mp4|srt|ass|sub)$', '', title.strip(), flags=re.I)
    return re.sub(r'[^a-z0-9]+', '', title.casefold())


def details(title: str) -> dict:
    s = title.casefold()
    spaced = re.sub(r'[^a-z0-9]+', ' ', s)
    tokens = set(spaced.split())
    resolution = next((x for x in ('2160p', '1080p', '720p', '480p') if x in tokens), None)
    source = None
    for kind, names in SOURCES.items():
        if any(re.search(r'(?<![a-z0-9])' + re.escape(n).replace(r'\ ', r'\s+') + r'(?![a-z0-9])', s) for n in names):
            source = kind
            break
    if not source and {'web', 'dl'} <= tokens:
        source = 'webdl'
    if not source and {'web', 'rip'} <= tokens:
        source = 'webrip'
    group = re.search(r'-([a-z0-9]{2,20})(?:\.(?:mkv|avi|mp4|srt))?$', s)
    edition = tokens & EDITION
    essential = {x for x in tokens if x not in COMMON and len(x) > 2 and not x.isdigit()}
    return {'resolution': resolution, 'source': source,
            'group': group.group(1) if group else None,
            'edition': edition, 'tokens': essential}


def score_pair(release: str, subtitle: str) -> dict:
    """One of exact, probable, possible, none; no media hash means never 'verified'."""
    if not release or not subtitle:
        return {'status': 'none', 'score': 0}
    if compact(release) == compact(subtitle):
        return {'status': 'exact', 'score': 100}
    a, b = details(release), details(subtitle)
    if a['resolution'] and b['resolution'] and a['resolution'] != b['resolution']:
        return {'status': 'none', 'score': 0}
    if a['source'] and b['source'] and a['source'] != b['source']:
        return {'status': 'none', 'score': 0}
    if a['edition'] != b['edition'] and (a['edition'] or b['edition']):
        return {'status': 'none', 'score': 0}
    group_equal = bool(a['group'] and b['group'] and a['group'] == b['group'])
    group_conflict = bool(a['group'] and b['group'] and a['group'] != b['group'])
    common = a['tokens'] & b['tokens']
    union = a['tokens'] | b['tokens']
    overlap = len(common) / len(union) if union else 0
    same_source = bool(a['source'] and a['source'] == b['source'])
    same_res = bool(a['resolution'] and a['resolution'] == b['resolution'])
    if group_equal and same_source and same_res:
        return {'status': 'probable', 'score': 90}
    if not group_conflict and same_source and same_res and overlap >= .65:
        return {'status': 'probable', 'score': 80}
    if same_source and same_res and overlap >= .35:
        return {'status': 'possible', 'score': 60}
    if overlap >= .82 and not group_conflict and (same_res or same_source):
        return {'status': 'possible', 'score': 55}
    return {'status': 'none', 'score': 0}


def compare_releases(releases: list[dict], subtitles: dict) -> dict:
    """Compare only OpenSubtitles results we actually fetched, never all in their catalogue."""
    priority = {'exact': 3, 'probable': 2, 'possible': 1, 'none': 0}
    out = []
    for release in releases:
        item = dict(release)
        matches = {}
        for lang in ('sv', 'en'):
            best = {'status': 'none', 'score': 0, 'subtitle': None}
            for sub in subtitles.get(lang, []):
                candidate = score_pair(item.get('title', ''), sub.get('release', ''))
                if (candidate['score'] > best['score']):
                    best = {**candidate, 'subtitle': {
                        'subtitle_id': sub.get('subtitle_id'),
                        'release': sub.get('release'),
                        'page_url': sub.get('page_url'),
                        'hearing_impaired': sub.get('hearing_impaired', False),
                        'machine_translated': sub.get('machine_translated', False),
                    }}
            matches[lang] = best
        item['matches'] = matches
        out.append(item)
    out.sort(key=lambda r: (bool(r.get('rejected')), -priority[r['matches']['sv']['status']],
                            -priority[r['matches']['en']['status']], r.get('title', '').casefold()))
    return {'releases': out,
            'sv_candidates': sum(r['matches']['sv']['status'] != 'none' for r in out if not r.get('rejected')),
            'en_candidates': sum(r['matches']['en']['status'] != 'none' for r in out if not r.get('rejected'))}
