"""
CivicPulse Louisville — Data Scraper
Center for Neighborhoods

Pulls Louisville Metro Appropriations Committee meetings from Swagit,
extracts NDF/CIF appropriation data, and writes to data/meetings.json.

Run manually:  python scraper/scrape.py
Runs on schedule via GitHub Actions (.github/workflows/scrape.yml)
"""

import json
import re
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ── CONFIG ────────────────────────────────────────────────────────────────────
SWAGIT_BASE     = "https://louisvilleky.new.swagit.com"
SEARCH_URL      = f"{SWAGIT_BASE}/search?q=appropriations+committee&sort=date_desc"
DATA_FILE       = Path(__file__).parent.parent / "data" / "meetings.json"
MAX_MEETINGS    = 20        # how many recent meetings to keep
REQUEST_TIMEOUT = 15        # seconds
HEADERS         = {"User-Agent": "CivicPulse-Louisville/1.0 (centerforneighborhoods.org; civic transparency research)"}


# ── HELPERS ───────────────────────────────────────────────────────────────────

def get(url: str) -> requests.Response:
    """GET with standard headers and timeout."""
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp


def parse_money(text: str) -> float:
    """Extract a dollar amount from text like '$12,000.00' or '12000'."""
    text = re.sub(r'[^\d.]', '', text.replace(',', ''))
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_districts(text: str) -> list:
    """
    Extract district numbers from text like:
    'District 5', 'Districts 3, 6, 7', '12th District', etc.
    """
    nums = re.findall(r'\b(\d{1,2})(?:st|nd|rd|th)?\s*[Dd]istrict|\b[Dd]istrict\s*(\d{1,2})', text)
    found = []
    for a, b in nums:
        d = a or b
        if d and d not in found:
            found.append(d)
    return found if found else []


def classify_type(text: str) -> str:
    """Classify an appropriation as NDF or CIF based on text."""
    text_up = text.upper()
    if 'CAPITAL' in text_up or 'CIF' in text_up or 'INFRASTRUCTURE' in text_up:
        return 'CIF'
    return 'NDF'


# ── SCRAPING ──────────────────────────────────────────────────────────────────

def fetch_meeting_list() -> list:
    """
    Get list of recent Appropriations Committee meetings from Swagit.
    Returns list of dicts: {id, date, committee, video_url}
    """
    print(f"  Fetching meeting list from Swagit…")
    meetings = []

    try:
        resp = get(SEARCH_URL)
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Swagit video cards — adapt selectors if Swagit updates their layout
        for card in soup.select('.video-card, .meeting-item, article.result'):
            link = card.select_one('a[href*="/videos/"]')
            if not link:
                continue
            href = link.get('href', '')
            vid_id = re.search(r'/videos/(\d+)', href)
            if not vid_id:
                continue

            date_el = card.select_one('.date, time, .meeting-date')
            title_el = card.select_one('.title, h2, h3, .meeting-title')

            date_str = ''
            if date_el:
                dt_attr = date_el.get('datetime', '') or date_el.get_text(strip=True)
                m = re.search(r'(\d{4}-\d{2}-\d{2})', dt_attr)
                if m:
                    date_str = m.group(1)

            title = title_el.get_text(strip=True) if title_el else 'Appropriations Committee'

            # Only include Appropriations Committee meetings
            if 'appropriation' not in title.lower() and 'appropriation' not in href.lower():
                continue

            meetings.append({
                'id': vid_id.group(1),
                'date': date_str,
                'committee': 'Appropriations Committee',
                'video_url': f"{SWAGIT_BASE}/videos/{vid_id.group(1)}",
                'title': title
            })

    except Exception as e:
        print(f"  WARNING: Meeting list fetch failed: {e}")
        print("  Falling back to known recent meeting IDs…")
        # Fallback: known recent meeting IDs — update manually if needed
        meetings = [
            {'id': '386028', 'date': '2026-05-06', 'committee': 'Appropriations Committee',
             'video_url': f"{SWAGIT_BASE}/videos/386028", 'title': 'May 06, 2026 Appropriations Committee'},
        ]

    print(f"  Found {len(meetings)} meeting(s)")
    return meetings[:MAX_MEETINGS]


def fetch_transcript(video_id: str) -> str:
    """
    Fetch closed caption / transcript text for a Swagit video.
    Returns plain text string (empty string if unavailable).
    """
    urls_to_try = [
        f"{SWAGIT_BASE}/videos/{video_id}/transcript",
        f"{SWAGIT_BASE}/videos/{video_id}/captions",
        f"{SWAGIT_BASE}/api/v1/videos/{video_id}/captions",
    ]
    for url in urls_to_try:
        try:
            resp = get(url)
            soup = BeautifulSoup(resp.text, 'html.parser')
            # Try to get transcript text from common containers
            for sel in ['.transcript-text', '.caption-text', '#transcript', 'article', 'main']:
                el = soup.select_one(sel)
                if el:
                    text = el.get_text(' ', strip=True)
                    if len(text) > 200:
                        return text
            # Fallback: full page text
            text = soup.get_text(' ', strip=True)
            if len(text) > 200:
                return text
        except Exception:
            continue
    return ''


def extract_appropriations(transcript: str, video_id: str) -> list:
    """
    Parse appropriation items from a meeting transcript.
    Returns list of appropriation dicts.

    This uses pattern matching on the transcript text.
    The patterns are tuned for Louisville Metro Appropriations Committee language.
    """
    items = []
    if not transcript:
        return items

    # Split into sentences/chunks
    chunks = re.split(r'(?<=[.!?])\s+|\n{2,}', transcript)

    # Patterns that indicate an appropriation item
    money_pattern = re.compile(r'\$[\d,]+(?:\.\d{2})?')
    item_triggers = ['appropriate', 'approp', 'ndf', 'neighborhood development fund',
                     'capital infrastructure', 'cif', 'allocate', 'transfer']

    item_num = 1
    for i, chunk in enumerate(chunks):
        chunk_lower = chunk.lower()
        if not any(t in chunk_lower for t in item_triggers):
            continue
        if not money_pattern.search(chunk):
            continue

        # Build context from surrounding chunks
        context = ' '.join(chunks[max(0,i-2):i+3])

        amounts = money_pattern.findall(context)
        if not amounts:
            continue
        amount = parse_money(amounts[0])
        if amount < 100:  # Skip tiny amounts — likely not appropriations
            continue

        districts = parse_districts(context)
        fund_type = classify_type(context)

        # Extract recipient — look for "to [Organization]" or "for [Organization]"
        recipient = ''
        rec_match = re.search(r'(?:to|for)\s+(?:the\s+)?([A-Z][A-Za-z\s&/,]+?)(?:\s+for|\s+to|\s+in\s+the\s+amount|,|\.|$)', context)
        if rec_match:
            recipient = rec_match.group(1).strip()[:80]

        # Determine vote result
        vote = 'Passed'
        if 'fail' in chunk_lower or 'reject' in chunk_lower or 'denied' in chunk_lower:
            vote = 'Failed'
        elif 'amend' in chunk_lower:
            vote = 'Passed (amended)'
        elif 'table' in chunk_lower or 'defer' in chunk_lower:
            vote = 'Tabled'

        # Clean up purpose text
        purpose = chunk.strip()[:200]

        items.append({
            'item': item_num,
            'type': fund_type,
            'amount': round(amount, 2),
            'districts': districts,
            'recipient': recipient or 'See source',
            'purpose': purpose,
            'sponsor': '',  # Hard to reliably extract — left blank for manual fill
            'vote': vote
        })
        item_num += 1

    return items


# ── MAIN ──────────────────────────────────────────────────────────────────────

def load_existing() -> dict:
    """Load existing data file, return empty structure if missing."""
    if DATA_FILE.exists():
        with open(DATA_FILE) as f:
            return json.load(f)
    return {'last_updated': '', 'meetings': []}


def save(data: dict):
    """Write data to JSON file."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"  Saved → {DATA_FILE}")


def scrape():
    print("=" * 60)
    print("CivicPulse Louisville — Scraper")
    print(f"Running at {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    existing = load_existing()
    existing_ids = {m['id'] for m in existing.get('meetings', [])}

    meetings = fetch_meeting_list()
    new_count = 0

    updated_meetings = list(existing.get('meetings', []))

    for mtg in meetings:
        if mtg['id'] in existing_ids:
            print(f"  Skipping {mtg['id']} (already in data)")
            continue

        print(f"\n  Processing meeting {mtg['id']} ({mtg.get('date', 'unknown date')})…")
        transcript = fetch_transcript(mtg['id'])
        print(f"  Transcript: {len(transcript)} chars")

        appropriations = extract_appropriations(transcript, mtg['id'])
        print(f"  Extracted {len(appropriations)} appropriation items")

        mtg_record = {
            'id': mtg['id'],
            'date': mtg.get('date', ''),
            'committee': mtg.get('committee', 'Appropriations Committee'),
            'video_url': mtg['video_url'],
            'appropriations': appropriations
        }
        updated_meetings.insert(0, mtg_record)
        new_count += 1

    # Keep only the most recent MAX_MEETINGS
    updated_meetings = updated_meetings[:MAX_MEETINGS]

    output = {
        'last_updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'),
        'meetings': updated_meetings
    }

    save(output)

    print(f"\n{'=' * 60}")
    print(f"Done. {new_count} new meeting(s) added. {len(updated_meetings)} total in data file.")
    print("=" * 60)

    return new_count


if __name__ == '__main__':
    try:
        scrape()
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
