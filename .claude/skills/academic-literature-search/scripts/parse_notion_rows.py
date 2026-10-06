#!/usr/bin/env python3
"""Convert a fetched Notion topic page (enhanced Markdown with <table> blocks) to rows JSON.

Used in update runs to recover the previous rows, and to import pages built by hand. The
parser is header-driven: each table's first row names its columns, so the standard
eight-column layout of this skill (Category | Title | Authors / Source / Year | Outlet /
Rank | Link | Key content | Relevance for the research question | Status), the German
seven-column layout of the teaching skill and hand-made tables all map onto the row schema
in references/output-format.md. The category comes from the row's Category cell, else from
the enclosing H3 heading.

Usage:
    python parse_notion_rows.py page.md -o rows.json
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

CATEGORY_ALIASES = {
    "books": ["books & book chapters", "books and book chapters", "books", "book",
              "book chapter", "book chapters", "chapter", "bücher", "buch", "e-book"],
    "articles": ["journal articles", "journal article", "articles", "article", "paper"],
    "unpublished": ["working papers & unpublished materials", "unpublished materials",
                    "unpublished", "working paper", "working papers", "preprint",
                    "preprints", "conference paper", "conference papers", "dissertation",
                    "thesis", "theses", "manuscript"],
    "reports": ["reports", "report", "white paper", "policy report", "industry report"],
    "data": ["data", "dataset", "datasets", "data source", "database", "daten", "datensatz"],
    "websites": ["websites", "website", "web", "portal", "documentation"],
    "blogs": ["blogs", "blog", "newsletter", "substack", "podcast"],
    "events": ["events & calls", "events", "event", "conference", "conferences",
               "special issue", "call for papers", "workshop", "communities"],
    "people": ["people", "person", "researcher", "researchers", "scholar", "scholars",
               "experts", "expert", "author", "authors", "personen"],
}
ALIAS_TO_KEY = {alias: key for key, aliases in CATEGORY_ALIASES.items() for alias in aliases}

# header cell (lower-cased, trimmed) -> row field
HEADER_FIELDS = {
    "category": "category", "kategorie": "category", "type": "category", "typ": "category",
    "title": "title", "titel": "title", "titel / name": "title", "name": "title",
    "title / name": "title",
    "authors / source / year": "author_source", "authors": "author_source",
    "author": "author_source", "autor": "author_source", "autor / quelle / firma": "author_source",
    "source": "author_source", "quelle": "author_source", "author/organisation": "author_source",
    "outlet / rank": "outlet_rank", "outlet": "outlet", "journal": "outlet", "rank": "rank",
    "ranking": "rank",
    "link": "link", "url": "link", "doi": "link", "links": "link",
    "key content": "note", "key finding": "note", "key finding / content": "note",
    "note": "note", "notes": "note", "notiz": "note", "summary": "note",
    "kurzbeschreibung": "note", "description": "note", "abstract": "abstract",
    "relevance for the research question": "relevance", "relevance": "relevance",
    "verwendung im kurs": "relevance", "use": "relevance",
    "status": "status", "year": "year", "jahr": "year", "access": "access",
}
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
URL_RE = re.compile(r"https?://\S+")


def trim_balanced(text: str) -> str:
    """Strip trailing punctuation and closing brackets that are not part of the URL/DOI.
    DOIs such as 10.1016/S0969-6997(01)00025-4 or SICI DOIs contain balanced brackets."""
    text = text.rstrip(".,;:'\"")
    changed = True
    while changed:
        changed = False
        for opening, closing in ("()", "[]", "<>"):
            if text.endswith(closing) and text.count(closing) > text.count(opening):
                text = text[:-1].rstrip(".,;:'\"")
                changed = True
    return text


def clean(cell: str) -> str:
    text = html.unescape(cell).replace("<br>", " ")
    text = LINK_RE.sub(lambda m: m.group(2) if URL_RE.match(m.group(2)) else m.group(1), text)
    text = re.sub(r"\\([\\*~`$\[\]<>{}|^])", r"\1", text)  # unescape Notion specials
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)             # drop bold markers
    return " ".join(text.split())


def category_key(value: str | None, fallback: str | None) -> str:
    text = (value or "").strip().lower().rstrip(" :")
    if text in ALIAS_TO_KEY:
        return ALIAS_TO_KEY[text]
    for alias, key in ALIAS_TO_KEY.items():
        if text.startswith(alias):
            return key
    return fallback or "websites"


def heading_key(heading: str) -> str | None:
    text = re.sub(r"\s*\(\d+\)\s*$", "", heading).strip().lower()
    return ALIAS_TO_KEY.get(text)


def parse_table(table: str, fallback: str | None) -> list[dict]:
    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", table, flags=re.S)
    if len(trs) < 2:
        return []
    header = [clean(c).lower() for c in re.findall(r"<td[^>]*>(.*?)</td>", trs[0], flags=re.S)]
    fields = [HEADER_FIELDS.get(h) for h in header]
    if "title" not in fields:
        return []  # not a source table
    rows = []
    for tr in trs[1:]:
        cells = [clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)]
        data = {field: cell for field, cell in zip(fields, cells) if field}
        if not data.get("title"):
            continue
        link = data.get("link") or ""
        m = URL_RE.search(link)
        if m:
            link = trim_balanced(m.group(0))
            for enc, dec in (("%28", "("), ("%29", ")"), ("%3C", "<"), ("%3E", ">"), ("%20", " ")):
                link = link.replace(enc, dec)
        author = data.get("author_source") or ""
        if data.get("year") and data["year"] not in author:
            author = ", ".join(filter(None, [author, data["year"]]))
        outlet, rank = data.get("outlet") or "", data.get("rank") or ""
        if data.get("outlet_rank"):
            parts = [p.strip() for p in data["outlet_rank"].split(";")]
            outlet = outlet or parts[0]
            rank = rank or "; ".join(parts[1:])
        rows.append({
            "category": category_key(data.get("category"), fallback),
            "title": data["title"], "author_source": author, "outlet": outlet, "rank": rank,
            "link": link, "note": data.get("note") or "",
            "relevance": data.get("relevance") or "",
            "status": data.get("status") or "manual; link unverified",
            "access": data.get("access") or "", "files": [],
        })
        m = re.search(r"\b(19|20)\d{2}\b", author)
        if m:
            rows[-1]["year"] = int(m.group(0))
    return rows


def parse(markdown: str) -> list[dict]:
    rows: list[dict] = []
    for block in re.split(r"(?=^### )", markdown, flags=re.M):
        heading = re.match(r"### (.+?)\s*$", block, flags=re.M)
        fallback = heading_key(heading.group(1)) if heading else None
        for table in re.findall(r"<table[^>]*>(.*?)</table>", block, flags=re.S):
            rows.extend(parse_table(table, fallback))
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("page", help="Markdown as returned by the Notion fetch tool")
    p.add_argument("-o", "--out", required=True)
    args = p.parse_args(argv)
    rows = parse(Path(args.page).read_text(encoding="utf-8"))
    Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(rows)} rows -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
