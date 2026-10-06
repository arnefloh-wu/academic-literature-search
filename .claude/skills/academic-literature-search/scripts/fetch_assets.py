#!/usr/bin/env python3
"""Download the files that may be stored in Dropbox and record them in the rows.

Only rows that look legally storable are fetched: `access` is free/open_access, or the URL
points at a PDF, dataset (csv, xlsx, zip, json, parquet, dta, sav, rds) or notebook on a
host that is not a paywalled publisher. Everything else is left as a link. The saved
filename is written into the row's "files" list so the Notion/README builder can mention it.

Usage:
    python fetch_assets.py rows.json -d "topics/<topic>/files"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

UA = "academic-literature-search/1.0 (academic research)"
STORABLE_EXT = (".pdf", ".csv", ".tsv", ".xlsx", ".xls", ".zip", ".json", ".parquet",
                ".dta", ".sav", ".rds", ".rdata", ".ipynb", ".qmd", ".rmd", ".txt")
PAYWALL_HOSTS = ("sciencedirect.com", "springer.com", "link.springer.com", "wiley.com",
                 "onlinelibrary.wiley.com", "tandfonline.com", "sagepub.com", "jstor.org",
                 "pubsonline.informs.org", "journals.ama.org", "academic.oup.com",
                 "cambridge.org", "emerald.com", "hbsp.harvard.edu", "thecasecentre.org",
                 "iveypublishing.ca", "statista.com", "youtube.com", "youtu.be",
                 "journals.aom.org", "ebsco.com", "proquest.com", "degruyter.com",
                 "elgaronline.com", "taylorfrancis.com", "routledge.com", "ingentaconnect.com")
MAX_BYTES = 200 * 1024 * 1024


def storable(row: dict) -> bool:
    url = (row.get("link") or "").lower()
    if not url.startswith("http") or any(h in url for h in PAYWALL_HOSTS):
        return False
    if row.get("access") in ("free", "open_access"):
        return url.split("?")[0].endswith(STORABLE_EXT) or row.get("category") in ("data",)
    return url.split("?")[0].endswith(STORABLE_EXT)


def safe_name(row: dict, url: str, content_type: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", (row.get("title") or "file"))[:80].strip("_")
    tail = url.split("?")[0].rsplit("/", 1)[-1]
    ext = Path(tail).suffix.lower()
    if not ext or len(ext) > 8:
        ext = {"application/pdf": ".pdf", "text/csv": ".csv", "application/zip": ".zip",
               "application/json": ".json"}.get(content_type.split(";")[0], ".bin")
    return f"{base}{ext}"


def download(url: str, dest_dir: Path, row: dict) -> Path | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        ctype = resp.headers.get("Content-Type", "")
        if "text/html" in ctype:
            return None  # landing page, not a file
        length = int(resp.headers.get("Content-Length") or 0)
        if length > MAX_BYTES:
            return None
        name = safe_name(row, resp.geturl(), ctype)
        dest = dest_dir / name
        with dest.open("wb") as f:
            total = 0
            while chunk := resp.read(1 << 20):
                total += len(chunk)
                if total > MAX_BYTES:
                    dest.unlink(missing_ok=True)
                    return None
                f.write(chunk)
    return dest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("rows")
    p.add_argument("-d", "--dest", required=True, help="download directory")
    p.add_argument("-o", "--out", help="output rows file (default: overwrite input)")
    args = p.parse_args(argv)

    rows_path = Path(args.rows)
    rows = json.loads(rows_path.read_text(encoding="utf-8"))
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)

    saved = 0
    for row in rows:
        row.setdefault("files", [])
        if not storable(row):
            continue
        try:
            path = download(row["link"], dest, row)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            print(f"skip {row.get('title')!r}: {getattr(e, 'reason', e)}", file=sys.stderr)
            continue
        if path and path.name not in row["files"]:
            row["files"].append(path.name)
            saved += 1
            print(f"saved {path.name}", file=sys.stderr)

    Path(args.out or rows_path).write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    print(f"{saved} files saved to {dest}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
