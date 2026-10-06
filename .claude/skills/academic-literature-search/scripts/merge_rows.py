#!/usr/bin/env python3
"""Merge rows from a previous run with rows from a new run (update mode).

Rows are matched on DOI, then on normalised link, then on normalised title. Matched rows
keep the old row's notes unless the new note is longer, and get the status prefix
"existing"; unmatched new rows get "new". Old rows not found again are kept (a re-run
should not silently drop a source the researcher already uses) with prefix "existing".

Usage:
    python merge_rows.py old_rows.json new_rows.json -o rows.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s]+", re.I)


def norm_title(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()[:120]


def norm_link(text: str | None) -> str:
    link = (text or "").strip().lower()
    link = re.sub(r"^https?://(www\.)?", "", link)
    return link.rstrip("/").split("?")[0]


def keys(row: dict) -> list[str]:
    out = []
    doi = DOI_RE.search(row.get("link") or "")
    if doi:
        out.append("doi:" + doi.group(0).lower().rstrip(".,;"))
    if row.get("link"):
        out.append("url:" + norm_link(row["link"]))
    if row.get("title"):
        out.append("title:" + norm_title(row["title"]))
    return out


def set_prefix(status: str | None, prefix: str) -> str:
    verification = (status or "link unverified").split(";")[-1].strip()
    return f"{prefix}; {verification}"


def merge(old: list[dict], new: list[dict]) -> list[dict]:
    index: dict[str, dict] = {}
    merged: list[dict] = []
    for row in old:
        row = dict(row)
        row["status"] = set_prefix(row.get("status"), "existing")
        merged.append(row)
        for k in keys(row):
            index.setdefault(k, row)
    added = 0
    for row in new:
        match = next((index[k] for k in keys(row) if k in index), None)
        if match is None:
            row = dict(row)
            row["status"] = set_prefix(row.get("status"), "new")
            merged.append(row)
            for k in keys(row):
                index.setdefault(k, row)
            added += 1
            continue
        for field in ("note", "relevance", "author_source", "outlet", "rank", "abstract"):
            if len(row.get(field) or "") > len(match.get(field) or ""):
                match[field] = row[field]
        if "link verified" in (row.get("status") or ""):
            match["status"] = "existing; link verified"
        for field in ("doi", "year", "authors", "item_type", "volume", "issue", "pages",
                      "publisher", "isbn", "access"):
            if row.get(field) and not match.get(field):
                match[field] = row[field]
        for f in row.get("files") or []:
            match.setdefault("files", [])
            if f not in match["files"]:
                match["files"].append(f)
    print(f"{len(old)} existing, {len(new)} new candidates, {added} added", file=sys.stderr)
    return merged


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("old")
    p.add_argument("new")
    p.add_argument("-o", "--out", required=True)
    args = p.parse_args(argv)
    old = json.loads(Path(args.old).read_text(encoding="utf-8"))
    new = json.loads(Path(args.new).read_text(encoding="utf-8"))
    Path(args.out).write_text(json.dumps(merge(old, new), ensure_ascii=False, indent=2),
                              encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
