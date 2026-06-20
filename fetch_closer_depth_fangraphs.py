"""
fetch_closer_depth_fangraphs.py
================================
Description: Scrapes the FanGraphs Roster Resource Closer Depth Chart and
             appends a dated snapshot to the Bronze data lake. Captures
             projected closer roles and key RP stats for all 30 MLB teams.
             Intended to run ~3x/week; deduplicates on
             (date_scraped, player_name, team) so re-runs are safe.

Source Data: FanGraphs Roster Resource
             https://www.fangraphs.com/roster-resource/closer-depth-chart

Outputs: data-lake/01_Bronze/fantasy_baseball/{year}_fangraphs_closers_depth.csv
         Columns: date_scraped, team, player_name, throws, role,
                  era, sv, hld, sd, md, k9, swstr_pct, k_pct, bb_pct,
                  hot_seat, on_rise
"""

import requests
import csv
import os
import sys
import argparse
from datetime import date
from html.parser import HTMLParser

# ---------------------------------------------------------------------------
# Project path setup
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball import mlb_processing as mp

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
URL = 'https://www.fangraphs.com/roster-resource/closer-depth-chart'

HTTP_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xhtml+xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Referer': 'https://www.fangraphs.com/',
}

# Row classes to skip entirely when parsing table rows
SKIP_ROW_CLASSES = {
    'menu-sub-header',
    'team-box_link__inactive__24Fnd',
    'closer-depth-charts__table__super-header',  # team section headers
    'super-header-spacer',                        # per-team column header rows
}

# Legacy constant kept for reference (the actual column-header class on the live page
# is 'super-header-spacer', handled via SKIP_ROW_CLASSES above).
HEADER_ROW_CLASS = 'align-right  fixed'

OUTPUT_FIELDS = [
    'date_scraped', 'team', 'player_name', 'throws', 'role',
    'era', 'sv', 'hld', 'sd', 'md',
    'k9', 'swstr_pct', 'k_pct', 'bb_pct',
    'hot_seat', 'on_rise',
]

# Stats are at the trailing end of every data row.
# Column order (right-to-left): BB/9, BB%, K/9, K%, SwStr%, MD, SD, HLD, SV, ERA
# BB/9 is captured but not written to the output schema (it's [-1]).
STAT_NEG_IDX = {
    'era':       -10,
    'sv':        -9,
    'hld':       -8,
    'sd':        -7,
    'md':        -6,
    'swstr_pct': -5,
    'k_pct':     -4,
    'k9':        -3,
    'bb_pct':    -2,
    # bb9 at [-1] exists but is not in OUTPUT_FIELDS
}

# Minimum cells in a valid data row
# 4 fixed (team/player/throws/role) + 1 tooltip + >=0 date cols + 10 stat cols
MIN_DATA_CELLS = 15


# ---------------------------------------------------------------------------
# HTML Parser
# ---------------------------------------------------------------------------

class TableParser(HTMLParser):
    """
    Parses every <tr> element in the page.

    For each row we record:
      - class     : the tr's class attribute (used to identify row type)
      - cells     : list of cell text strings (whitespace-collapsed)
      - cell4_meta: accumulated attribute values from all tags inside cell[4],
                    used to detect Hot Seat / On the Rise badges even when
                    the badge is rendered as a CSS icon with no visible text
                    (aria-label, title, data-tip, class names are all captured).
    """

    def __init__(self):
        super().__init__()
        self.rows = []
        self._in_row = False
        self._row_class = ''
        self._cells = []
        self._in_cell = False
        self._depth = 0
        self._cell_parts = []
        self._cell_idx = 0
        self._cell4_meta = []   # raw attribute strings from inside cell[4]

    # ------------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)

        if tag == 'tr':
            self._in_row = True
            self._row_class = attrs_d.get('class', '')
            self._cells = []
            self._cell_idx = 0
            self._cell4_meta = []
            self._in_cell = False
            self._depth = 0

        elif tag in ('td', 'th') and self._in_row:
            if not self._in_cell:
                self._in_cell = True
                self._depth = 1
                self._cell_parts = []
            else:
                self._depth += 1
                self._capture_cell4_attrs(attrs_d)

        elif self._in_cell:
            self._depth += 1
            self._capture_cell4_attrs(attrs_d)

    def _capture_cell4_attrs(self, attrs_d):
        """Capture attribute values of elements inside cell[4] for badge detection."""
        if self._cell_idx != 4:
            return
        for key in ('class', 'aria-label', 'title', 'data-tip', 'data-for'):
            val = attrs_d.get(key, '').strip()
            if val:
                self._cell4_meta.append(val)

    # ------------------------------------------------------------------
    def handle_endtag(self, tag):
        if not self._in_row:
            return

        if tag == 'tr':
            self.rows.append({
                'class':      self._row_class,
                'cells':      self._cells[:],
                'cell4_meta': ' '.join(self._cell4_meta),
            })
            self._in_row = False
            self._in_cell = False

        elif tag in ('td', 'th') and self._in_cell:
            self._depth -= 1
            if self._depth == 0:
                text = ' '.join(self._cell_parts).strip()
                self._cells.append(text)
                self._in_cell = False
                self._cell_idx += 1
                self._cell_parts = []

        elif self._in_cell:
            self._depth -= 1

    # ------------------------------------------------------------------
    def handle_data(self, data):
        if self._in_cell:
            s = data.strip()
            if s:
                self._cell_parts.append(s)


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

def fetch_html(url, verify_ssl=True):
    """
    GET the page HTML.  On SSL errors (common on corporate proxies) retries
    once with certificate verification disabled.
    """
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=30, verify=verify_ssl)
        resp.raise_for_status()
        resp.encoding = 'utf-8'   # force UTF-8; requests defaults to Latin-1 when charset is absent
        return resp.text
    except requests.exceptions.SSLError:
        if verify_ssl:
            print('  SSL certificate error — retrying without verification...')
            return fetch_html(url, verify_ssl=False)
        raise


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _clean(val):
    """Strip whitespace / percent signs; map placeholder values to empty string."""
    v = val.strip().replace('%', '')
    return '' if v in ('-', '—', '', 'N/A', 'null') else v


def _detect_badge(cells, cell4_meta):
    """
    Return (hot_seat, on_rise) booleans.

    Checks:
      1. Visible text in cell[4] (some themes render text labels).
      2. Accumulated CSS class names / aria-label / title / data-tip strings
         collected from every element inside cell[4].
    """
    cell4_text = (cells[4].lower() if len(cells) > 4 else '')
    meta_lower = cell4_meta.lower()

    hot_seat = (
        'hot seat'     in cell4_text or
        'hot seat'     in meta_lower or
        'hotseat'      in meta_lower or
        'hot_seat'     in meta_lower or
        'hot-seat'     in meta_lower
    )
    on_rise = (
        'on the rise'  in cell4_text or
        'on the rise'  in meta_lower or
        'ontherise'    in meta_lower or
        'on_the_rise'  in meta_lower or
        'on-the-rise'  in meta_lower or
        'onrise'       in meta_lower
    )
    return hot_seat, on_rise


def parse_players(html):
    """
    Parse the FanGraphs page and return a list of player dicts.

    Row classification:
      - Skip rows whose class contains any of SKIP_ROW_CLASSES.
      - Skip the column-header row (class contains HEADER_ROW_CLASS).
      - Process only rows with class == '' (empty string = data rows).

    Cell layout in data rows:
      [0]  team abbreviation (e.g. 'ATH')
      [1]  player name
      [2]  throws (R/L/S)
      [3]  projected role
      [4]  MUI Tooltip / badge cell (skip text, inspect metadata for badges)
      [5..N-10]  recent-usage date columns (variable count — ignored)
      [-10] ERA
      [-9]  SV
      [-8]  HLD
      [-7]  SD
      [-6]  MD
      [-5]  SwStr%
      [-4]  K%
      [-3]  K/9
      [-2]  BB%
      [-1]  BB/9  (present but not in output schema)
    """
    parser = TableParser()
    parser.feed(html)

    players = []
    for row in parser.rows:
        cls = row['class']

        # --- skip non-data rows ---
        if any(skip in cls for skip in SKIP_ROW_CLASSES):
            continue
        if HEADER_ROW_CLASS in cls:
            continue
        if cls != '':
            continue

        cells = row['cells']
        if len(cells) < MIN_DATA_CELLS:
            continue
        if not cells[1]:          # blank player name -> spurious empty row
            continue
        if cells[1] == 'PLAYER':  # stray column-header row with empty class
            continue
        if cells[0] == 'TEAM':    # safety net for any header row variant
            continue

        hot_seat, on_rise = _detect_badge(cells, row['cell4_meta'])

        player = {
            'team':        cells[0],
            'player_name': cells[1],
            'throws':      cells[2],
            'role':        cells[3],
            'hot_seat':    hot_seat,
            'on_rise':     on_rise,
        }
        for field, neg_idx in STAT_NEG_IDX.items():
            try:
                player[field] = _clean(cells[neg_idx])
            except IndexError:
                player[field] = ''

        players.append(player)

    return players


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------

def load_existing(filepath):
    """Return (list_of_rows, set_of_dedup_keys) from an existing CSV, or empty."""
    rows = []
    keys = set()
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                rows.append(row)
                keys.add((row['date_scraped'], row['player_name'], row['team']))
    return rows, keys


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Scrape FanGraphs Closer Depth Chart → Bronze data lake.'
    )
    parser.add_argument(
        '--year', type=int, default=date.today().year,
        help='Season year (default: current year)'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Parse and print results without writing to disk'
    )
    args = parser.parse_args()

    today_str = date.today().strftime('%Y-%m-%d')
    output_file = os.path.join(mp.DATA_PATH, f'{args.year}_fangraphs_closers_depth.csv')

    print(f'=== FanGraphs Closer Depth Chart — {today_str} ===')
    print(f'URL: {URL}')

    html = fetch_html(URL)
    print(f'  HTML fetched: {len(html):,} bytes')

    players = parse_players(html)
    print(f'  Players parsed: {len(players)}')

    if not players:
        print('  WARNING: 0 players parsed — page structure may have changed.')
        print('           No file written.')
        return

    # Stamp every row with today's date
    for p in players:
        p['date_scraped'] = today_str

    # Deduplicate within this scrape: the page renders each team's pitchers
    # in multiple sub-table views (pitcher usage, results, etc.), producing
    # duplicate rows per player. Keep the first occurrence per (player_name, team).
    seen_within = set()
    deduped = []
    for p in players:
        key = (p['player_name'], p['team'])
        if key not in seen_within:
            seen_within.add(key)
            deduped.append(p)
    if len(deduped) < len(players):
        print(f'  Within-scrape dedup: {len(players)} -> {len(deduped)} rows '
              f'({len(players) - len(deduped)} duplicates removed)')
    players = deduped

    # ---- dry-run: print sample and exit ----
    if args.dry_run:
        print(f'\n[DRY RUN] Would write {len(players)} rows -> {output_file}')
        print(f'  {"TEAM":<5} {"PLAYER":<26} {"ROLE":<24} {"ERA":>5} {"SV":>3} '
              f'{"SD":>3} {"MD":>3} {"K/9":>5} {"HOT":>4} {"RISE":>4}')
        print('  ' + '-' * 85)
        for p in players[:10]:
            print(f'  {p["team"]:<5} {p["player_name"]:<26} {p["role"]:<24} '
                  f'{p["era"]:>5} {p["sv"]:>3} {p["sd"]:>3} {p["md"]:>3} '
                  f'{p["k9"]:>5} '
                  f'{"Y" if p["hot_seat"] else "":>4} '
                  f'{"Y" if p["on_rise"] else "":>4}')
        if len(players) > 10:
            print(f'  ... and {len(players) - 10} more rows')
        return

    # ---- live run: dedup and write ----
    existing_rows, existing_keys = load_existing(output_file)

    new_rows = [
        p for p in players
        if (p['date_scraped'], p['player_name'], p['team']) not in existing_keys
    ]

    if not new_rows:
        print(f'  Already current — 0 new rows '
              f'(all {len(players)} players already recorded for {today_str}).')
        return

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(existing_rows)
        writer.writerows(new_rows)

    total = len(existing_rows) + len(new_rows)
    print(f'  Wrote {len(new_rows)} new rows -> {output_file}')
    print(f'  File total: {total} rows ({len(existing_rows)} prior + {len(new_rows)} new)')

    # ── Write run log ─────────────────────────────────────────────────────────
    try:
        import json as _json
        from datetime import datetime as _dt
        _log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'data-lake', '00_Logs', 'fantasy_baseball')
        os.makedirs(_log_dir, exist_ok=True)
        _entry = {
            'ts'             : _dt.now().isoformat(timespec='seconds'),
            'workflow'       : 'fantasy-collect-fangraphs-closers',
            'status'         : 'ok',
            'csv_path'       : output_file,
            'csv_total_rows' : total,
            'rows_written'   : len(new_rows),
            'latest_scrape'  : today_str,
        }
        with open(os.path.join(_log_dir, 'fantasy-collect-fangraphs-closers.jsonl'), 'a', encoding='utf-8') as _f:
            _f.write(_json.dumps(_entry) + '\n')
    except Exception as _e:
        print(f'[WARN] run-log write failed: {_e}')


if __name__ == '__main__':
    main()
