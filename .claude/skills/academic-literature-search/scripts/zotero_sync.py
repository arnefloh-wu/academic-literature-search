#!/usr/bin/env python3
"""Push the references of a topic into Zotero (Web API v3, standard library only).

Creates (once) the top-level collection "Academic Literature Search", a subcollection
named after the topic, and one Zotero item per reference row (books, articles, unpublished,
reports, data, websites, blogs). Items already in the subcollection (same DOI or URL) are
skipped, so re-runs only add what is new. Each created item's key is written back into the
row as "zotero_key". Tags: the topic and the category.

Credentials (.env in the skill folder or environment): ZOTERO_API_KEY (zotero.org >
Settings > Security > Create new private key, with library write access), ZOTERO_USER_ID
(shown on the same page), optional ZOTERO_LIBRARY_TYPE=group and ZOTERO_LIBRARY_ID for a
group library.

Usage:
    python zotero_sync.py topics/<topic>/rows.json --topic "<topic>"
    python zotero_sync.py topics/<topic>/rows.json --topic "<topic>" --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_bibliography import (BIB_CATEGORIES, authors_of, doi_of, item_type,  # noqa: E402
                                year_of)
from search_sources import env, load_env  # noqa: E402

API = "https://api.zotero.org"
ROOT_COLLECTION = "Academic Literature Search"
BATCH = 50


def base() -> str:
    kind = (env("ZOTERO_LIBRARY_TYPE") or "user").lower()
    if kind == "group":
        lib = env("ZOTERO_LIBRARY_ID")
        if not lib:
            raise SystemExit("ZOTERO_LIBRARY_ID is required for a group library")
        return f"{API}/groups/{lib}"
    uid = env("ZOTERO_USER_ID")
    if not uid:
        raise SystemExit("Set ZOTERO_USER_ID and ZOTERO_API_KEY in .env (see .env.example)")
    return f"{API}/users/{uid}"


def call(method: str, path: str, params: dict | None = None, data=None,
         headers: dict | None = None):
    url = f"{base()}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Zotero-API-Version", "3")
    req.add_header("Zotero-API-Key", env("ZOTERO_API_KEY") or "")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                return (json.loads(text) if text else {}), dict(resp.headers)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 3:
                time.sleep(int(e.headers.get("Backoff") or e.headers.get("Retry-After") or 5))
                continue
            raise RuntimeError(f"Zotero {e.code} {e.reason} for {method} {path}: "
                               f"{e.read().decode(errors='replace')[:300]}") from e
    raise RuntimeError("Zotero: too many retries")


def paged(path: str, params: dict | None = None) -> list[dict]:
    out, start = [], 0
    while True:
        page, headers = call("GET", path, {**(params or {}), "limit": 100, "start": start})
        out.extend(page)
        total = int(headers.get("Total-Results", len(out)))
        start += 100
        if start >= total or not page:
            return out


def ensure_collection(name: str, parent: str | None, dry: bool) -> str:
    cols = paged("/collections")
    for c in cols:
        d = c["data"]
        if d["name"] == name and (d.get("parentCollection") or None) == parent:
            return c["key"]
    if dry:
        return f"<new collection {name!r}>"
    payload = [{"name": name, "parentCollection": parent or False}]
    res, _ = call("POST", "/collections", data=payload)
    key = (res.get("successful") or {}).get("0", {}).get("key") or res.get("success", {}).get("0")
    if not key:
        raise RuntimeError(f"collection not created: {res}")
    return key


def existing_identifiers(collection: str) -> dict[str, str]:
    ids: dict[str, str] = {}
    for it in paged(f"/collections/{collection}/items", {"format": "json"}):
        d = it.get("data", {})
        for value in (d.get("DOI"), d.get("url")):
            if value:
                ids[norm(value)] = it["key"]
        m = re.search(r"DOI:\s*(\S+)", d.get("extra") or "")
        if m:
            ids[norm(m.group(1))] = it["key"]
    return ids


def norm(value: str) -> str:
    v = value.strip().lower()
    v = re.sub(r"^https?://(dx\.)?doi\.org/", "", v)
    v = re.sub(r"^https?://(www\.)?", "", v)
    return v.rstrip("/").split("?")[0]


def creators(row: dict) -> list[dict]:
    out = []
    for a in authors_of(row):
        if "literal" in a:
            out.append({"creatorType": "author", "name": a["literal"]})
        else:
            out.append({"creatorType": "author", "lastName": a["family"],
                        "firstName": a.get("given", "")})
    for e in row.get("editors") or []:
        from build_bibliography import split_name
        n = split_name(e)
        if n:
            out.append({"creatorType": "editor", **({"name": n["literal"]} if "literal" in n else
                                                   {"lastName": n["family"], "firstName": n.get("given", "")})})
    return out


def to_item(row: dict, topic: str, collection: str) -> dict:
    t = item_type(row)
    outlet = row.get("outlet") or ""
    y = year_of(row)
    item = {"itemType": t, "title": row.get("title") or "", "creators": creators(row),
            "abstractNote": row.get("abstract") or "", "date": y if y != "n.d." else "",
            "url": row.get("link") or "", "collections": [collection],
            "tags": [{"tag": topic}, {"tag": row.get("category") or ""}],
            "extra": ""}
    doi = doi_of(row)
    extra = []
    if row.get("rank"):
        extra.append(f"Journal rank: {row['rank']}")
    if row.get("note"):
        extra.append(f"Key content: {row['note']}")
    if row.get("relevance"):
        extra.append(f"Relevance: {row['relevance']}")
    fields_by_type = {
        "journalArticle": {"publicationTitle": outlet, "volume": row.get("volume"),
                           "issue": row.get("issue"), "pages": row.get("pages"), "DOI": doi},
        "book": {"publisher": row.get("publisher") or outlet, "ISBN": row.get("isbn")},
        "bookSection": {"bookTitle": row.get("book_title") or outlet,
                        "publisher": row.get("publisher"), "pages": row.get("pages"),
                        "ISBN": row.get("isbn")},
        "report": {"institution": row.get("publisher") or outlet,
                   "reportNumber": row.get("report_number")},
        "preprint": {"repository": outlet, "DOI": doi},
        "conferencePaper": {"proceedingsTitle": outlet, "DOI": doi, "pages": row.get("pages")},
        "thesis": {"university": row.get("publisher") or outlet, "thesisType": "Doctoral dissertation"},
        "dataset": {"repository": row.get("publisher") or outlet, "DOI": doi},
        "webpage": {"websiteTitle": outlet or row.get("publisher")},
        "blogPost": {"blogTitle": outlet or row.get("publisher")},
        "manuscript": {"manuscriptType": "Working paper"},
    }
    for k, v in fields_by_type.get(t, {}).items():
        if v:
            item[k] = str(v)
    if doi and "DOI" not in item:
        extra.insert(0, f"DOI: {doi}")
    item["extra"] = "\n".join(extra)
    return item


def main(argv: list[str] | None = None) -> int:
    load_env()
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("rows")
    p.add_argument("--topic", required=True, help="subcollection name (the topic as typed)")
    p.add_argument("--root", default=ROOT_COLLECTION, help="top-level collection name")
    p.add_argument("--dry-run", action="store_true", help="print the items, write nothing")
    args = p.parse_args(argv)

    rows_path = Path(args.rows)
    rows = json.loads(rows_path.read_text(encoding="utf-8"))
    refs = [r for r in rows if r.get("category") in BIB_CATEGORIES and r.get("title")]

    if args.dry_run and not (env("ZOTERO_API_KEY") and (env("ZOTERO_USER_ID") or env("ZOTERO_LIBRARY_ID"))):
        items = [to_item(r, args.topic, "<collection>") for r in refs]
        print(json.dumps(items, ensure_ascii=False, indent=2))
        print(f"dry run without credentials: {len(items)} items would be created", file=sys.stderr)
        return 0

    root = ensure_collection(args.root, None, args.dry_run)
    sub = ensure_collection(args.topic.replace("/", " & "), root, args.dry_run)
    known = existing_identifiers(sub) if not args.dry_run else {}

    todo, skipped = [], 0
    for r in refs:
        ids = [norm(x) for x in (doi_of(r), r.get("link")) if x]
        hit = next((known[i] for i in ids if i in known), None)
        if hit or r.get("zotero_key"):
            r.setdefault("zotero_key", hit)
            skipped += 1
            continue
        todo.append(r)

    if args.dry_run:
        print(json.dumps([to_item(r, args.topic, sub) for r in todo], ensure_ascii=False, indent=2))
        print(f"dry run: {len(todo)} items would be created in {args.root} / {args.topic}; "
              f"{skipped} already present", file=sys.stderr)
        return 0

    created = failed = 0
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        res, _ = call("POST", "/items", data=[to_item(r, args.topic, sub) for r in chunk])
        for idx, info in (res.get("successful") or {}).items():
            chunk[int(idx)]["zotero_key"] = info.get("key")
            created += 1
        for idx, err in (res.get("failed") or {}).items():
            failed += 1
            print(f"failed: {chunk[int(idx)].get('title')!r}: {err.get('message')}", file=sys.stderr)
        rows_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Zotero: {created} created, {skipped} already present, {failed} failed -> "
          f"{args.root} / {args.topic}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
