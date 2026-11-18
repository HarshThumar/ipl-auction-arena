"""Track, fetch, hash, and archive expert/pundit post-retention preview articles.

Component F (Expert-consensus needs) & Failure Mode B5 mitigation:
Guarantees point-in-time veracity with no post-auction edits or hindsight leakage.
Metadata is stored in data/reference/expert_articles_2027.csv.
Raw fetched HTML is stored locally under data/raw/expert_articles_2027/ (gitignored).

Run:
  python scripts/archive_expert_articles.py --fetch
  python scripts/archive_expert_articles.py --check-wayback
  python scripts/archive_expert_articles.py --report
"""
import argparse, csv, hashlib, json, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF_CSV = ROOT / "data" / "reference" / "expert_articles_2027.csv"
RAW_DIR = ROOT / "data" / "raw" / "expert_articles_2027"

SEED_ARTICLES = [
    {
        "id": "EXP-2027-01",
        "outlet": "Wisden",
        "title": "IPL 2027 Retention List: Full List of Retained and Released Players",
        "publish_date": "2026-11-17",
        "live_url": "https://www.wisden.com/series/ipl-2027/cricket-news/ipl-2027-retention-list-full-list-retained-released",
        "author": "Wisden Staff",
    },
    {
        "id": "EXP-2027-02",
        "outlet": "Crictracker",
        "title": "IPL 2027: 5 Biggest Surprises from Retention Announcement",
        "publish_date": "2026-11-18",
        "live_url": "https://www.crictracker.com/cricket-appeal/ipl-2027-retentions-5-biggest-surprises-from-the-announcement/",
        "author": "Crictracker Staff",
    },
    {
        "id": "EXP-2027-03",
        "outlet": "Crictracker",
        "title": "IPL 2027: Full List of Confirmed Trades Ahead of the Auction",
        "publish_date": "2026-11-17",
        "live_url": "https://www.crictracker.com/cricket-news/ipl-2027-full-list-of-confirmed-trades-ahead-of-the-auction/",
        "author": "Crictracker Staff",
    },
    {
        "id": "EXP-2027-04",
        "outlet": "Hindustan Times",
        "title": "IPL 2027 Retention: Full list of retained, released players and remaining purse",
        "publish_date": "2026-11-17",
        "live_url": "https://www.hindustantimes.com/cricket/ipl-2027-retention-full-list-of-retained-released-players-and-remaining-purse-of-all-10-teams-101794928401303.html",
        "author": "HT Sports Desk",
    },
]

FIELDNAMES = [
    "id",
    "outlet",
    "title",
    "publish_date",
    "author",
    "live_url",
    "wayback_save_url",
    "wayback_archive_url",
    "local_snapshot",
    "sha256",
    "status",
]


def load_rows():
    if not REF_CSV.exists():
        rows = []
        for a in SEED_ARTICLES:
            row = dict(a)
            row["wayback_save_url"] = f"https://web.archive.org/save/{a['live_url']}"
            row["wayback_archive_url"] = ""
            row["local_snapshot"] = ""
            row["sha256"] = ""
            row["status"] = "pending"
            rows.append(row)
        save_rows(rows)
        return rows
    with open(REF_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_rows(rows):
    REF_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(REF_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)


def fetch_snapshots(rows):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for r in rows:
        fn = f"{r['id']}_{r['outlet'].lower().replace(' ', '_')}.html"
        p = RAW_DIR / fn
        if not p.exists() or not r.get("sha256"):
            print(f"Fetching {r['id']} ({r['outlet']})...")
            try:
                req = urllib.request.Request(r["live_url"], headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                content = urllib.request.urlopen(req, timeout=20).read()
                p.write_bytes(content)
                digest = hashlib.sha256(content).hexdigest()
                r["local_snapshot"] = f"data/raw/expert_articles_2027/{fn}"
                r["sha256"] = digest
                if r["status"] == "pending":
                    r["status"] = "captured_local"
                print(f"  Saved {len(content)} bytes, sha256={digest[:12]}...")
            except Exception as e:
                print(f"  Error fetching {r['live_url']}: {e}")
        else:
            print(f"{r['id']}: local snapshot exists ({r['local_snapshot']})")
    save_rows(rows)


def check_wayback(rows):
    updated = False
    for r in rows:
        live = r["live_url"]
        api = f"https://archive.org/wayback/available?url={live}"
        try:
            req = urllib.request.Request(api, headers={"User-Agent": "Mozilla/5.0"})
            res = urllib.request.urlopen(req, timeout=15)
            data = json.loads(res.read().decode("utf-8"))
            snap = data.get("archived_snapshots", {}).get("closest")
            if snap and snap.get("available") and snap.get("url"):
                archived = snap["url"]
                if r.get("wayback_archive_url") != archived:
                    r["wayback_archive_url"] = archived
                    r["status"] = "archived_wayback"
                    updated = True
                    print(f"[{r['id']}] Found Wayback snapshot: {archived}")
            else:
                print(f"[{r['id']}] Not yet in Wayback archive. Save link: {r['wayback_save_url']}")
        except Exception as e:
            print(f"[{r['id']}] Error checking Wayback: {e}")
    if updated:
        save_rows(rows)


def print_report(rows):
    print("\n=== Expert Articles Tracked for 2027 Needs (Component F / B5) ===")
    for r in rows:
        print(f"[{r['id']}] {r['outlet']} - {r['title'][:55]}...")
        print(f"       Date: {r['publish_date']} | Author: {r['author']}")
        print(f"       Status: {r['status']}")
        print(f"       SHA256: {r['sha256'][:16]}..." if r['sha256'] else "       SHA256: none")
        print(f"       Live:   {r['live_url']}")
        print(f"       Save:   {r['wayback_save_url']}")
        if r.get("wayback_archive_url"):
            print(f"       Archive:{r['wayback_archive_url']}")
        print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="Download local HTML snapshots and compute SHA256")
    ap.add_argument("--check-wayback", action="store_true", help="Poll Wayback Machine API for archive URLs")
    ap.add_argument("--report", action="store_true", help="Print summary report")
    args = ap.parse_args()

    rows = load_rows()
    if args.fetch:
        fetch_snapshots(rows)
    if args.check_wayback:
        check_wayback(rows)
    if args.report or (not args.fetch and not args.check_wayback):
        print_report(rows)


if __name__ == "__main__":
    main()
