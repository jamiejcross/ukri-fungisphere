#!/usr/bin/env python3
"""
UKRI Fungisphere — GTR Data Updater
====================================
Queries the UKRI Gateway to Research (GTR) API for active fungal research
projects and writes updated CSV files to data/.

Usage:
    python update_data.py               # full update
    python update_data.py --dry-run     # preview only, no write
    python update_data.py --help        # show options

API docs: https://gtr.ukri.org/resources/GtR-2-API-v1.7.5.pdf
"""

import csv
import json
import time
import argparse
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode, quote

# ── Configuration ──────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent / "data"

# Keywords to search. Multiple terms per string use GTR's OR syntax.
SEARCH_TERMS = [
    "fungi",
    "fungal",
    "mould",
    "mushroom",
    "mycorrhiza",
    "Aspergillus",
    "Candida",
    "Fusarium",
    "Penicillium",
    "Trichoderma",
    "yeast",
    "lichen",
    "mycotoxin",
    "mycelium",
    "antifungal",
]

# Broad social science / humanities indicator terms
SOCIAL_SCIENCE_CLASSIFIERS = {
    "social science/sociology": [
        "social science", "sociology", "sociol", "social theory",
        "social policy", "social inequal", "inequalit",
    ],
    "arts/humanities": [
        "arts", "humanities", "literary", "cultural studies",
        "fiction", "narrative", "genre", "film", "literature",
    ],
    "ethnography/cultural": [
        "ethnograph", "anthropolog", "cultural", "qualitative",
        "interview", "fieldwork",
    ],
    "policy/governance": [
        "policy", "governance", "regulation", "legislation",
        "public health policy", "government",
    ],
    "housing/damp/mould": [
        "damp", "mould in home", "mold in home", "housing",
        "indoor air", "building", "respiratory",
    ],
    "anthropocene/multispecies": [
        "anthropocene", "multispecies", "more-than-human",
        "nonhuman", "posthuman", "speculative",
    ],
    "inequality/justice": [
        "inequalit", "justice", "race", "class", "poverty",
        "marginalised", "marginalized",
    ],
}

GTR_BASE = "https://gtr.ukri.org"
FETCH_SIZE = 100          # max per page
REQUEST_DELAY = 0.4       # seconds between API requests (be polite)
MAX_PAGES_PER_TERM = 20   # safety cap per search term

# ── API helpers ────────────────────────────────────────────────────────────────

def gtr_get(path: str, params: dict = None) -> dict:
    """Fetch a GTR API endpoint and return parsed JSON."""
    url = GTR_BASE + path
    if params:
        url += "?" + urlencode(params)
    req = Request(url, headers={
        "Accept": "application/vnd.rcuk.gtr.json-v7",
        "User-Agent": "ukri-fungisphere/1.0 (research dashboard; contact via GitHub)",
    })
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


_org_cache: dict[str, str] = {}

def fetch_org_name(org_id: str) -> str:
    """Fetch and cache an organisation name by ID."""
    if org_id in _org_cache:
        return _org_cache[org_id]
    try:
        data = gtr_get(f"/gtr/api/organisations/{org_id}")
        name = data.get("name", "")
        _org_cache[org_id] = name
        time.sleep(REQUEST_DELAY)
        return name
    except Exception:
        return ""


def fetch_fund_value(fund_id: str) -> str:
    """Fetch grant value in pounds from the fund endpoint."""
    try:
        data = gtr_get(f"/gtr/api/funds/{fund_id}")
        vp = data.get("valuePounds") or {}
        amount = vp.get("amount", "")
        time.sleep(REQUEST_DELAY)
        return str(amount) if amount != "" else ""
    except Exception:
        return ""


def search_projects(term: str) -> list[dict]:
    """Return all project records matching a search term."""
    results = []
    page = 1

    while page <= MAX_PAGES_PER_TERM:
        params = {
            "q": f'"{term}"',
            "n": FETCH_SIZE,
            "p": page,
        }
        try:
            data = gtr_get("/gtr/api/projects", params)
        except (URLError, HTTPError) as e:
            print(f"  ⚠ API error for '{term}' page {page}: {e}", file=sys.stderr)
            break

        hits = data.get("project", [])
        if not hits:
            break

        results.extend(hits)
        total_pages = int(data.get("totalPages", 1))
        if page >= total_pages:
            break
        page += 1
        time.sleep(REQUEST_DELAY)

    return results


def _ms_to_date(ms) -> str:
    """Convert a millisecond timestamp to YYYY-MM-DD, or return empty string."""
    if not ms:
        return ""
    try:
        from datetime import timezone
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return ""


def extract_project(raw: dict) -> dict | None:
    """Flatten a GTR API v2 project into a CSV-compatible dict."""
    proj_id = raw.get("id", "")
    if not proj_id:
        return None

    links = raw.get("links", {}).get("link", [])

    # Lead org: prefer participantValues (no extra call), else fetch from API
    lead_org = ""
    grant_offer = ""
    participants = (raw.get("participantValues") or {}).get("participant", [])
    for p in participants:
        if p.get("role") == "LEAD_PARTICIPANT":
            lead_org = p.get("organisationName", "")
            amount = p.get("grantOffer", "")
            grant_offer = str(amount) if amount != "" else ""
            break

    if not lead_org:
        lead_org_links = [l for l in links if l.get("rel") == "LEAD_ORG"]
        if lead_org_links:
            org_id = lead_org_links[0]["href"].rstrip("/").split("/")[-1]
            lead_org = fetch_org_name(org_id)

    # Dates and fund value from FUND link
    start_date = ""
    end_date = ""
    fund_links = [l for l in links if l.get("rel") == "FUND"]
    if fund_links:
        fl = fund_links[0]
        start_date = _ms_to_date(fl.get("start"))
        end_date = _ms_to_date(fl.get("end"))
        if not grant_offer:
            fund_id = fl["href"].rstrip("/").split("/")[-1]
            grant_offer = fetch_fund_value(fund_id)

    return {
        "title": raw.get("title", "").strip(),
        "abstract": (raw.get("abstractText") or "").strip(),
        "id": proj_id,
        "grant_category": raw.get("grantCategory", ""),
        "grant_offer": grant_offer,
        "start_date": start_date,
        "end_date": end_date,
        "funder_name": raw.get("leadFunder", ""),
        "lead_org": lead_org,
        "tech_abstract": (raw.get("techAbstractText") or "").strip(),
        "potential_impact": (raw.get("potentialImpact") or "").strip(),
        "status": raw.get("status", "Active"),
    }


# ── Social science classification ──────────────────────────────────────────────

def classify_social_science(row: dict) -> str | None:
    """
    Return a pipe-separated string of matching SS themes, or None.
    Checks title + abstract + potential_impact.
    """
    text = " ".join([
        row.get("title", ""),
        row.get("abstract", ""),
        row.get("potential_impact", ""),
    ]).lower()

    matched = []
    for theme, keywords in SOCIAL_SCIENCE_CLASSIFIERS.items():
        if any(kw.lower() in text for kw in keywords):
            matched.append(theme)

    return "; ".join(matched) if matched else None


# ── Main ───────────────────────────────────────────────────────────────────────

def run(dry_run: bool = False):
    print(f"\n{'='*60}")
    print(f"  UKRI Fungisphere — GTR Data Update")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    if dry_run:
        print("  DRY RUN — no files will be written.\n")

    # Phase 1: collect unique raw project records across all search terms.
    # Deduplication happens here, before any expensive org/fund API calls.
    unique_raws: dict[str, dict] = {}   # keyed by project id

    for term in SEARCH_TERMS:
        print(f"  Searching: '{term}'…", end=" ", flush=True)
        raw_results = search_projects(term)
        new_count = 0
        for raw in raw_results:
            pid = raw.get("id", "")
            if pid and pid not in unique_raws:
                unique_raws[pid] = raw
                new_count += 1
        print(f"{new_count} new / {len(raw_results)} total results")
        time.sleep(REQUEST_DELAY)

    print(f"\n  Total unique projects: {len(unique_raws)}")
    print(f"  Fetching institution and funding details…\n")

    # Phase 2: enrich each unique project (org + fund calls happen once per project).
    all_rows: dict[str, dict] = {}
    for i, (pid, raw) in enumerate(unique_raws.items(), 1):
        row = extract_project(raw)
        if row:
            all_rows[pid] = row
        if i % 50 == 0:
            print(f"    {i}/{len(unique_raws)} enriched…")

    # Convert to list and sort by title
    projects = sorted(all_rows.values(), key=lambda r: r.get("title", "").lower())

    # Classify social science
    ss_projects = []
    for row in projects:
        themes = classify_social_science(row)
        if themes:
            ss_row = dict(row)
            ss_row["social_science_themes"] = themes
            ss_projects.append(ss_row)

    print(f"  Social science projects identified: {len(ss_projects)}")

    if dry_run:
        print("\n  Sample rows (first 3):")
        for r in projects[:3]:
            print(f"    - {r['title'][:70]}")
        print("\n  Dry run complete. No files written.")
        return

    # Write main CSV
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    main_path = DATA_DIR / "active_mould_fungi_projects.csv"
    main_fields = [
        "title", "abstract", "id", "grant_category", "grant_offer",
        "start_date", "end_date", "funder_name", "lead_org",
        "tech_abstract", "potential_impact", "status",
    ]
    with open(main_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=main_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(projects)
    print(f"\n  ✓ Wrote {len(projects)} rows → {main_path}")

    # Write social science CSV
    ss_path = DATA_DIR / "active_mould_fungi_social_science.csv"
    ss_fields = main_fields + ["social_science_themes"]
    with open(ss_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ss_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(ss_projects)
    print(f"  ✓ Wrote {len(ss_projects)} rows → {ss_path}")

    # Write a small metadata file for the dashboard to read
    meta = {
        "last_updated": datetime.now().isoformat(),
        "total_projects": len(projects),
        "social_science_projects": len(ss_projects),
        "search_terms": SEARCH_TERMS,
    }
    meta_path = DATA_DIR / "metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"  ✓ Wrote metadata → {meta_path}")

    print(f"\n  Update complete.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Update UKRI Fungisphere data from the GTR API."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Query the API but do not write any files."
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run)
