#!/usr/bin/env python3
"""Check the Link of every curated row and set the Status label accordingly.

Input/output: a JSON list of rows (see references/output-format.md). Rows whose link
answers 2xx/3xx become "link verified"; a 404/410 downgrades a "verified" claim to
"link unverified". Publisher pages that block robots (401, 403, 429) and network failures
keep the status the agent assigned, and the HTTP result is recorded in the row's
"link_check" field so the instructor can see why.

Usage:
    python verify_links.py rows.json            # rewrite in place
    python verify_links.py rows.json -o out.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
URL_RE = re.compile(r"https?://[^\s)\]>]+")
VERIFIED = "link verified"
UNVERIFIED = "link unverified"


def extract_url(link: str | None) -> str | None:
    if not link:
        return None
    match = URL_RE.search(link)
    return match.group(0).rstrip(".,;") if match else None


def check(url: str, timeout: int = 20) -> tuple[int | None, str]:
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.geturl()
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (400, 403, 405, 501):
                continue  # many servers reject HEAD; retry with GET
            return e.code, url
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if method == "HEAD":
                continue
            return None, f"network: {getattr(e, 'reason', e)}"
    return None, "unreachable"


def set_status(status: str | None, label: str) -> str:
    """Replace the verification part of 'new; <label>' while keeping the prefix."""
    status = status or f"new; {UNVERIFIED}"
    prefix = status.split(";")[0].strip() if ";" in status else "new"
    return f"{prefix}; {label}"


def verify(rows: list[dict], workers: int = 8) -> list[dict]:
    urls = [extract_url(r.get("link")) for r in rows]

    def job(i: int):
        return i, (check(urls[i]) if urls[i] else (None, "no link"))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, (code, info) in pool.map(job, range(len(rows))):
            row = rows[i]
            if code is not None and 200 <= code < 400:
                row["status"] = set_status(row.get("status"), VERIFIED)
                row["link_check"] = f"{code}"
            else:
                row["link_check"] = f"{code or ''} {info}".strip()
                # Only a definite "gone" answer overrides the agent's own check; robot
                # blocks (401/403/429) and network failures prove nothing about the link.
                if code in (404, 410) and VERIFIED in (row.get("status") or ""):
                    row["status"] = set_status(row.get("status"), UNVERIFIED)
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("rows", help="JSON file with a list of rows")
    p.add_argument("-o", "--out", help="output file (default: overwrite input)")
    args = p.parse_args(argv)

    path = Path(args.rows)
    rows = json.loads(path.read_text(encoding="utf-8"))
    rows = verify(rows)
    Path(args.out or path).write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    ok = sum(VERIFIED in (r.get("status") or "") for r in rows)
    print(f"{ok}/{len(rows)} links verified", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
