#!/usr/bin/env python3
"""Push the references of a topic into Zotero (Web API v3, standard library only).

Default target is a Zotero **group library** (recommended: a private group called
"Academic Literature Search"). Each topic becomes a top-level collection in that group,
with one Zotero item per reference row (books, articles, unpublished, reports, data,
websites, blogs). Items already in the collection (same DOI or URL) are skipped, so
re-runs only add what is new. The created item key is written back into each row as
"zotero_key". Tags: the topic and the category. Key content, relevance and journal rank go
into the item's Extra field.

Credentials, read from the environment or from .env in the skill folder:
    ZOTERO_KEY          required (alias: ZOTERO_API_KEY). zotero.org/settings/keys/new with
                        read/write access to the group (and optionally the personal library)
    ZOTERO_GROUP        the group: numeric ID, group URL (https://www.zotero.org/groups/<ID>/...)
                        or group name (aliases: ZOTERO_GROUP_ID, ZOTERO_GROUP_NAME)
    ZOTERO_USER_ID      optional; detected from the key when missing
    ZOTERO_ROOT_COLLECTION  optional parent collection for all topics (default: none in a
                        group, "Academic Literature Search" in the personal library)
Without a group ID or name the personal library is used.
Older variables ZOTERO_LIBRARY_TYPE=group + ZOTERO_LIBRARY_ID still work.

--group overrides ZOTERO_GROUP for one run, so each search can go to its own group while
the environment holds only the key (give the key read/write access to "all groups").

Usage:
    python zotero_sync.py --check                       # key, permissions, groups, target
    python zotero_sync.py --check --group "Coauthor project X"
    python zotero_sync.py topics/<topic>/rows.json --topic "<topic>" --group 1234567
    python zotero_sync.py topics/<topic>/rows.json --topic "<topic>" --dry-run
    python zotero_sync.py topics/<topic>/rows.json --topic "<topic>"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_bibliography import (BIB_CATEGORIES, authors_of, doi_of, item_type,  # noqa: E402
                                split_name, year_of)
from search_sources import env, load_env  # noqa: E402

USER_ROOT_COLLECTION = "Academic Literature Search"
BATCH = 50


def set_group(value: str) -> None:
    """Point the sync at one group: a numeric ID, a group URL or a group name."""
    for name in ("ZOTERO_GROUP_ID", "ZOTERO_GROUP_NAME", "ZOTERO_LIBRARY_ID"):
        os.environ.pop(name, None)
    value = value.strip()
    m = re.fullmatch(r"\d+", value) or re.search(r"/groups/(\d+)", value)
    if m:
        os.environ["ZOTERO_GROUP_ID"] = m.group(1) if m.lastindex else m.group(0)
    else:
        os.environ["ZOTERO_GROUP_NAME"] = value


def apply_aliases(group_override: str | None = None) -> None:
    """Map the short variable names onto the ones the code reads:
    ZOTERO_KEY -> ZOTERO_API_KEY; ZOTERO_GROUP -> ZOTERO_GROUP_ID when it is a number or a
    group URL, else ZOTERO_GROUP_NAME. Explicitly set long names win over ZOTERO_GROUP;
    a --group value wins over everything."""
    if env("ZOTERO_KEY") and not env("ZOTERO_API_KEY"):
        os.environ["ZOTERO_API_KEY"] = env("ZOTERO_KEY")
    if group_override:
        set_group(group_override)
        return
    group = env("ZOTERO_GROUP")
    if group and not (env("ZOTERO_GROUP_ID") or env("ZOTERO_GROUP_NAME")):
        set_group(group)


def api_root() -> str:
    return (env("ZOTERO_API_BASE") or "https://api.zotero.org").rstrip("/")


class ZoteroError(RuntimeError):
    pass


def request(method: str, url: str, params: dict | None = None, data=None) -> tuple:
    """One Zotero API call with retries on 429/503; returns (json, headers)."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    body = json.dumps(data).encode() if data is not None else None
    key = env("ZOTERO_API_KEY")
    if not key:
        raise ZoteroError("ZOTERO_KEY is not set (see .env.example and SKILL.md, "
                          "section 'Zotero group setup')")
    for attempt in range(4):
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Zotero-API-Version", "3")
        req.add_header("Zotero-API-Key", key)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                return (json.loads(text) if text else {}), dict(resp.headers)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 3:
                time.sleep(int(e.headers.get("Backoff") or e.headers.get("Retry-After") or 5))
                continue
            detail = e.read().decode(errors="replace")[:300]
            hint = {403: " (key lacks access or write permission for this library)",
                    404: " (library or collection not found: check the group ID)"}.get(e.code, "")
            if e.code == 403 and url.endswith("/keys/current"):
                hint = " (invalid or revoked API key)"
            raise ZoteroError(f"Zotero {e.code} {e.reason} for {method} "
                              f"{url.replace(api_root(), '')}{hint}: {detail}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ZoteroError(f"cannot reach {api_root()}: {getattr(e, 'reason', e)}. In a "
                              f"cloud session, add api.zotero.org to the allowed domains.") from e
    raise ZoteroError("Zotero: too many retries")


def key_info() -> dict:
    """GET /keys/current: userID, username and access rights of the API key."""
    info, _ = request("GET", f"{api_root()}/keys/current")
    return info


def user_groups(user_id) -> list[dict]:
    groups, _ = request("GET", f"{api_root()}/users/{user_id}/groups", {"limit": 100})
    return [{"id": g.get("id"), "name": (g.get("data") or {}).get("name", ""),
             "type": (g.get("data") or {}).get("type", "")} for g in groups]


def can_write(info: dict, group_id: int | None) -> bool:
    access = info.get("access") or {}
    if group_id is None:
        return bool((access.get("user") or {}).get("write"))
    groups = access.get("groups") or {}
    perm = groups.get(str(group_id)) or groups.get("all") or {}
    return bool(perm.get("write"))


class Library:
    """The target library: personal (/users/<id>) or group (/groups/<id>)."""

    def __init__(self, info: dict | None = None):
        self.info = info
        group_id = env("ZOTERO_GROUP_ID")
        if not group_id and (env("ZOTERO_LIBRARY_TYPE") or "").lower() == "group":
            group_id = env("ZOTERO_LIBRARY_ID")
        group_name = env("ZOTERO_GROUP_NAME")
        self.group_id: int | None = None
        self.name = "personal library"
        if group_id or group_name:
            if group_id:
                self.group_id = int(group_id)
                self.name = f"group {group_name or group_id}"
            else:
                groups = user_groups(self.user_id())
                match = [g for g in groups if g["name"].lower() == group_name.lower()]
                if not match:
                    names = ", ".join(f"{g['name']} ({g['id']})" for g in groups) or "none"
                    raise ZoteroError(f"no group named {group_name!r} for this key; groups: {names}")
                self.group_id = int(match[0]["id"])
                self.name = f"group {match[0]['name']}"
            self.prefix = f"{api_root()}/groups/{self.group_id}"
        else:
            self.prefix = f"{api_root()}/users/{self.user_id()}"

    def user_id(self):
        if env("ZOTERO_USER_ID"):
            return env("ZOTERO_USER_ID")
        if self.info is None:
            self.info = key_info()
        return self.info["userID"]

    def default_root(self) -> str | None:
        configured = env("ZOTERO_ROOT_COLLECTION")
        if configured is not None:
            return configured or None
        return None if self.group_id else USER_ROOT_COLLECTION

    def writable(self) -> bool:
        if self.info is None:
            self.info = key_info()
        return can_write(self.info, self.group_id)

    def call(self, method: str, path: str, params: dict | None = None, data=None):
        return request(method, f"{self.prefix}{path}", params, data)

    def paged(self, path: str, params: dict | None = None) -> list[dict]:
        out, start = [], 0
        while True:
            page, headers = self.call("GET", path, {**(params or {}), "limit": 100, "start": start})
            out.extend(page)
            total = int(headers.get("Total-Results", len(out)))
            start += 100
            if start >= total or not page:
                return out


def ensure_collection(lib: Library, name: str, parent: str | None, dry: bool) -> str:
    for c in lib.paged("/collections"):
        d = c["data"]
        if d["name"] == name and (d.get("parentCollection") or None) == parent:
            return c["key"]
    if dry:
        return f"<new collection {name!r}>"
    res, _ = lib.call("POST", "/collections",
                      data=[{"name": name, "parentCollection": parent or False}])
    key = ((res.get("successful") or {}).get("0") or {}).get("key") or \
        (res.get("success") or {}).get("0")
    if not key:
        raise ZoteroError(f"collection {name!r} not created: {res}")
    return key


def existing_identifiers(lib: Library, collection: str) -> dict[str, str]:
    ids: dict[str, str] = {}
    for it in lib.paged(f"/collections/{collection}/items", {"format": "json"}):
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
    return v.rstrip("/")


def creators(row: dict) -> list[dict]:
    out = []
    for a in authors_of(row):
        if "literal" in a:
            out.append({"creatorType": "author", "name": a["literal"]})
        else:
            out.append({"creatorType": "author", "lastName": a["family"],
                        "firstName": a.get("given", "")})
    for e in row.get("editors") or []:
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


def check() -> int:
    """Print what the key can do and which library the sync would write to."""
    info = key_info()
    print(f"API key belongs to {info.get('username')} (userID {info.get('userID')})")
    access = info.get("access") or {}
    user = access.get("user") or {}
    print(f"personal library: read {bool(user.get('library'))}, write {bool(user.get('write'))}")
    groups = user_groups(info["userID"])
    if groups:
        print("groups:")
        for g in groups:
            print(f"  {g['id']:>10}  {g['name']}  ({g['type']}; key can write: "
                  f"{can_write(info, int(g['id']))})")
    else:
        print("groups: none (create one at https://www.zotero.org/groups/new)")
    lib = Library(info)
    ok = lib.writable()
    root = lib.default_root()
    print(f"target: {lib.name} -> {lib.prefix.replace(api_root(), '')}; topics as "
          f"{'sub-collections of ' + repr(root) if root else 'top-level collections'}; "
          f"write access: {ok}")
    if not ok:
        print("The key cannot write to the target library: edit the key at "
              "https://www.zotero.org/settings/keys and grant read/write for the group.",
              file=sys.stderr)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    load_env()
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("rows", nargs="?")
    p.add_argument("--topic", help="collection name (the topic as typed)")
    p.add_argument("--root", help="parent collection for all topics; '' for none "
                                  "(default: none in a group library)")
    p.add_argument("--group", help="target group for this run: ID, group URL or name "
                                   "(overrides ZOTERO_GROUP)")
    p.add_argument("--check", action="store_true", help="verify key, permissions and target")
    p.add_argument("--dry-run", action="store_true", help="print the items, write nothing")
    args = p.parse_args(argv)
    apply_aliases(args.group)

    try:
        if args.check:
            return check()
        if not args.rows or not args.topic:
            p.error("rows file and --topic are required (or use --check)")

        rows_path = Path(args.rows)
        rows = json.loads(rows_path.read_text(encoding="utf-8"))
        refs = [r for r in rows if r.get("category") in BIB_CATEGORIES and r.get("title")]
        topic = args.topic.replace("/", " & ")

        if args.dry_run and not env("ZOTERO_API_KEY"):
            items = [to_item(r, args.topic, "<collection>") for r in refs]
            print(json.dumps(items, ensure_ascii=False, indent=2))
            print(f"dry run without credentials: {len(items)} items would be created",
                  file=sys.stderr)
            return 0

        lib = Library()
        if not lib.writable():
            raise ZoteroError(f"the API key cannot write to the {lib.name}; run --check")
        root_name = args.root if args.root is not None else lib.default_root()
        root = ensure_collection(lib, root_name, None, args.dry_run) if root_name else None
        coll = ensure_collection(lib, topic, root, args.dry_run)
        known = existing_identifiers(lib, coll) if not coll.startswith("<") else {}
        where = f"{lib.name} / {(root_name + ' / ') if root_name else ''}{topic}"

        todo, skipped = [], 0
        for r in refs:
            ids = [norm(x) for x in (doi_of(r), r.get("link")) if x]
            hit = next((known[i] for i in ids if i in known), None)
            if hit:
                r["zotero_key"] = hit
                skipped += 1
                continue
            todo.append(r)

        if args.dry_run:
            print(json.dumps([to_item(r, args.topic, coll) for r in todo],
                             ensure_ascii=False, indent=2))
            print(f"dry run: {len(todo)} items would be created in {where}; "
                  f"{skipped} already present", file=sys.stderr)
            return 0

        created = failed = 0
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            res, _ = lib.call("POST", "/items",
                              data=[to_item(r, args.topic, coll) for r in chunk])
            for idx, info in (res.get("successful") or {}).items():
                chunk[int(idx)]["zotero_key"] = info.get("key")
                created += 1
            for idx, err in (res.get("failed") or {}).items():
                failed += 1
                print(f"failed: {chunk[int(idx)].get('title')!r}: {err.get('message')}",
                      file=sys.stderr)
            rows_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        rows_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Zotero: {created} created, {skipped} already present, {failed} failed -> {where}",
              file=sys.stderr)
        return 1 if failed else 0
    except ZoteroError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
