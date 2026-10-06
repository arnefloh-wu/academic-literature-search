#!/usr/bin/env python3
"""Build the bibliography of a topic from rows.json: CSL-JSON, BibTeX, RIS and APA 7.

Rows in the categories books, articles, unpublished, reports, data, websites and blogs
become references; people and events are skipped. The row fields used are title, authors
(list) or author_source (free text, parsed as a fallback), year, outlet, volume, issue,
pages, publisher, editors, isbn, doi, link, abstract and item_type (Zotero item type:
journalArticle, book, bookSection, report, preprint, conferencePaper, thesis, dataset,
webpage, blogPost, manuscript). Missing item types are inferred from the category.

Outputs (all standard library, Zotero and Word import the first three directly):
    <stem>.json   CSL-JSON (Zotero: File > Import; also used by zotero_sync.py)
    <stem>.bib    BibTeX
    <stem>.ris    RIS
    <stem>.md     APA 7 reference list, alphabetical, with DOI links

Usage:
    python build_bibliography.py topics/<topic>/rows.json -o topics/<topic>/bibliography
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BIB_CATEGORIES = {"books", "articles", "unpublished", "reports", "data", "websites", "blogs"}
CATEGORY_TYPE = {"books": "book", "articles": "journalArticle", "unpublished": "manuscript",
                 "reports": "report", "data": "dataset", "websites": "webpage",
                 "blogs": "blogPost"}
CSL_TYPE = {"journalArticle": "article-journal", "book": "book", "bookSection": "chapter",
            "report": "report", "preprint": "article", "conferencePaper": "paper-conference",
            "thesis": "thesis", "dataset": "dataset", "webpage": "webpage",
            "blogPost": "post-weblog", "manuscript": "manuscript"}
BIB_TYPE = {"journalArticle": "article", "book": "book", "bookSection": "incollection",
            "report": "techreport", "preprint": "unpublished", "conferencePaper": "inproceedings",
            "thesis": "phdthesis", "dataset": "misc", "webpage": "misc", "blogPost": "misc",
            "manuscript": "unpublished"}
RIS_TYPE = {"journalArticle": "JOUR", "book": "BOOK", "bookSection": "CHAP", "report": "RPRT",
            "preprint": "UNPB", "conferencePaper": "CPAPER", "thesis": "THES", "dataset": "DATA",
            "webpage": "ELEC", "blogPost": "BLOG", "manuscript": "UNPB"}
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\])]+", re.I)
YEAR_RE = re.compile(r"\b(1[89]|20)\d{2}[a-z]?\b")


# ------------------------------------------------------------------ names and fields

def split_name(name: str) -> dict:
    """'Family, Given' or 'Given Family' -> {'family': ..., 'given': ...}; organisations
    (no space, or marked with braces) become literal names."""
    name = " ".join(name.strip().strip("{}").split())
    if not name:
        return {}
    if "," in name:
        family, given = [p.strip() for p in name.split(",", 1)]
        return {"family": family, "given": given}
    parts = name.split(" ")
    if len(parts) == 1 or any(k in name for k in ("University", "Bank", "OECD", "Institute",
                                                   "Commission", "Organisation", "Organization",
                                                   "Group", "Inc", "Ltd", "GmbH", "Agency")):
        return {"literal": name}
    particles = {"van", "von", "de", "der", "den", "del", "da", "di", "la", "le", "du"}
    i = len(parts) - 1
    while i > 1 and parts[i - 1].lower() in particles:
        i -= 1
    return {"family": " ".join(parts[i:]), "given": " ".join(parts[:i])}


def looks_like_given(text: str) -> bool:
    """'Yves L.', 'T. K.', 'Bing-Sheng' -> True; 'Harvard Business School Press' -> False."""
    tokens = text.strip().split()
    return 0 < len(tokens) <= 3 and all(t[0].isupper() for t in tokens) and \
        not any(k.lower() in text.lower() for k in ("press", "university", "journal", "review"))


def parse_author_source(text: str) -> list[str]:
    """Fallback when a row has no `authors` list: take the author part of strings such as
    'Doz, Yves L. and Hamel, Gary, Harvard Business School Press, 1998, book' or
    'Spiller, Fitzsimons, Lynch and McClelland, Journal of Marketing Research 50(2), 2013'."""
    head = re.split(r",\s*(?:(?:[A-Z][^,]*?\s)?(?:Journal|Review|Science|Management|Studies|Press|"
                    r"University|Report|Working Paper|Quarterly|Economics|Business|Publishing|"
                    r"Oxford|Cambridge|Springer|Routledge|Elgar|Palgrave|Wiley|SSRN|NBER)[^,]*)",
                    text, maxsplit=1)[0]
    head = re.split(r"\s*\(\d{4}", head)[0]
    head = re.split(r",\s*(?:19|20)\d{2}\b", head)[0]
    chunks = re.split(r"\s*(?:,\s*)?(?:\band\b|&|\bund\b)\s*", head)
    names: list[str] = []
    for chunk in chunks:
        parts = [c.strip() for c in chunk.split(",") if c.strip()]
        if not parts:
            continue
        if len(parts) == 2 and looks_like_given(parts[1]):
            names.append(f"{parts[0]}, {parts[1]}")       # Family, Given
        elif len(parts) % 2 == 0 and all(looks_like_given(parts[i]) for i in range(1, len(parts), 2)):
            names += [f"{parts[i]}, {parts[i + 1]}" for i in range(0, len(parts), 2)]
        else:
            names += parts                                 # Given Family, Given Family
    return [n for n in names if not YEAR_RE.fullmatch(n)][:12]


def initials(given: str) -> str:
    return " ".join(f"{p[0]}." if not p.endswith(".") else p
                    for part in given.split() for p in part.split("-") if p)


def authors_of(row: dict) -> list[dict]:
    names = row.get("authors") or []
    if isinstance(names, str):
        names = [n.strip() for n in re.split(r";|\band\b|&", names) if n.strip()]
    if not names and row.get("author_source"):
        names = parse_author_source(row["author_source"])
    return [n for n in (split_name(x) for x in names) if n]


def year_of(row: dict) -> str:
    if row.get("year"):
        return str(row["year"])
    m = YEAR_RE.search(row.get("author_source") or "")
    return m.group(0) if m else "n.d."


def doi_of(row: dict) -> str | None:
    for field in ("doi", "link"):
        m = DOI_RE.search(row.get(field) or "")
        if m:
            return m.group(0).rstrip(".,;")
    return None


def item_type(row: dict) -> str:
    t = (row.get("item_type") or "").strip()
    if t in CSL_TYPE:
        return t
    src = (row.get("author_source") or "").lower()
    cat = row.get("category")
    if cat == "books" and ("chapter" in src or " in:" in src or "bookSection" in t):
        return "bookSection"
    if cat == "unpublished":
        if "conference" in src or "proceedings" in src or "annual meeting" in src:
            return "conferencePaper"
        if "dissertation" in src or "thesis" in src:
            return "thesis"
        if any(k in src for k in ("ssrn", "arxiv", "preprint", "working paper", "nber", "cepr")):
            return "preprint"
    return CATEGORY_TYPE.get(cat, "webpage")


def cite_key(row: dict, used: set[str]) -> str:
    auth = authors_of(row)
    fam = (auth[0].get("family") or auth[0].get("literal") or "anon") if auth else "anon"
    fam = re.sub(r"[^A-Za-z]", "", fam.split()[-1]) or "anon"
    word = next((w for w in re.findall(r"[A-Za-z]{4,}", row.get("title") or "")
                 if w.lower() not in {"with", "from", "that", "this", "their", "into"}), "")
    base = f"{fam}{year_of(row).rstrip('abcdefghij')}{word.lower()}"
    key, i = base, 1
    while key in used:
        i += 1
        key = f"{base}{i}"
    used.add(key)
    return key


# ------------------------------------------------------------------------- formats

def to_csl(row: dict, key: str) -> dict:
    t = item_type(row)
    item = {"id": key, "type": CSL_TYPE[t], "title": row.get("title") or ""}
    auth = authors_of(row)
    if auth:
        item["author"] = auth
    if row.get("editors"):
        item["editor"] = [split_name(e) for e in row["editors"]]
    y = year_of(row)
    if y != "n.d.":
        item["issued"] = {"date-parts": [[int(y[:4])]]}
    outlet = row.get("outlet") or ""
    if t in ("journalArticle", "conferencePaper", "preprint", "blogPost", "webpage", "dataset"):
        if outlet:
            item["container-title"] = outlet
    elif t == "bookSection":
        if row.get("book_title") or outlet:
            item["container-title"] = row.get("book_title") or outlet
    if t in ("book", "bookSection", "report", "thesis", "dataset", "manuscript"):
        pub = row.get("publisher") or (outlet if t != "bookSection" else "")
        if pub:
            item["publisher"] = pub
    for src, dst in (("volume", "volume"), ("issue", "issue"), ("pages", "page"),
                     ("isbn", "ISBN"), ("abstract", "abstract"), ("report_number", "number")):
        if row.get(src):
            item[dst] = str(row[src])
    doi = doi_of(row)
    if doi:
        item["DOI"] = doi
    if row.get("link"):
        item["URL"] = row["link"]
    if t == "preprint":
        item["genre"] = "Preprint"
    if t == "thesis":
        item["genre"] = "Doctoral dissertation"
    return item


def bib_escape(text: str) -> str:
    return re.sub(r"([&%$#_])", r"\\\1", str(text or ""))


def to_bibtex(row: dict, key: str) -> str:
    t = item_type(row)
    fields = {"title": f"{{{bib_escape(row.get('title'))}}}"}
    auth = authors_of(row)
    if auth:
        fields["author"] = " and ".join(
            f"{{{a['literal']}}}" if "literal" in a else f"{a['family']}, {a.get('given', '')}".strip(", ")
            for a in auth)
    if row.get("editors"):
        fields["editor"] = " and ".join(
            f"{n['family']}, {n.get('given', '')}".strip(", ") if "family" in n else f"{{{n['literal']}}}"
            for n in (split_name(e) for e in row["editors"]) if n)
    y = year_of(row)
    if y != "n.d.":
        fields["year"] = y[:4]
    outlet = row.get("outlet") or ""
    if t == "journalArticle" and outlet:
        fields["journal"] = bib_escape(outlet)
    elif t == "bookSection" and (row.get("book_title") or outlet):
        fields["booktitle"] = bib_escape(row.get("book_title") or outlet)
    elif t == "conferencePaper" and outlet:
        fields["booktitle"] = bib_escape(outlet)
    elif t in ("book", "report", "thesis", "dataset", "manuscript", "preprint") and (row.get("publisher") or outlet):
        name = "institution" if t == "report" else "school" if t == "thesis" else "publisher"
        fields[name] = bib_escape(row.get("publisher") or outlet)
    if t in ("preprint", "manuscript"):
        fields["note"] = bib_escape(outlet or "Working paper")
    for src, dst in (("volume", "volume"), ("issue", "number"), ("pages", "pages"),
                     ("isbn", "isbn"), ("abstract", "abstract")):
        if row.get(src):
            fields[dst] = bib_escape(str(row[src]).replace("-", "--") if src == "pages" else row[src])
    doi = doi_of(row)
    if doi:
        fields["doi"] = doi
    if row.get("link"):
        fields["url"] = row["link"]
    body = ",\n".join(f"  {k} = {{{v}}}" if not v.startswith("{") else f"  {k} = {v}"
                      for k, v in fields.items())
    return f"@{BIB_TYPE[t]}{{{key},\n{body}\n}}\n"


def to_ris(row: dict) -> str:
    t = item_type(row)
    lines = [f"TY  - {RIS_TYPE[t]}", f"TI  - {row.get('title') or ''}"]
    for a in authors_of(row):
        lines.append("AU  - " + (a["literal"] if "literal" in a else f"{a['family']}, {a.get('given', '')}".strip(", ")))
    for e in row.get("editors") or []:
        n = split_name(e)
        lines.append("A2  - " + (n.get("literal") or f"{n.get('family', '')}, {n.get('given', '')}".strip(", ")))
    y = year_of(row)
    if y != "n.d.":
        lines.append(f"PY  - {y[:4]}")
    outlet = row.get("outlet") or ""
    if t in ("journalArticle", "conferencePaper", "bookSection", "blogPost", "webpage"):
        if row.get("book_title") or outlet:
            lines.append(f"T2  - {row.get('book_title') or outlet}")
    if row.get("publisher") or (t in ("book", "report", "thesis", "dataset", "preprint", "manuscript") and outlet):
        lines.append(f"PB  - {row.get('publisher') or outlet}")
    if row.get("volume"):
        lines.append(f"VL  - {row['volume']}")
    if row.get("issue"):
        lines.append(f"IS  - {row['issue']}")
    if row.get("pages"):
        pages = str(row["pages"]).replace("–", "-")
        sp, _, ep = pages.partition("-")
        lines.append(f"SP  - {sp.strip()}")
        if ep.strip():
            lines.append(f"EP  - {ep.strip()}")
    if row.get("isbn"):
        lines.append(f"SN  - {row['isbn']}")
    doi = doi_of(row)
    if doi:
        lines.append(f"DO  - {doi}")
    if row.get("link"):
        lines.append(f"UR  - {row['link']}")
    if row.get("abstract"):
        lines.append(f"AB  - {' '.join(str(row['abstract']).split())}")
    if row.get("note"):
        lines.append(f"N1  - {' '.join(str(row['note']).split())}")
    lines.append("ER  - ")
    return "\n".join(lines) + "\n"


def apa_authors(auth: list[dict]) -> str:
    def one(a: dict) -> str:
        if "literal" in a:
            return a["literal"]
        return f"{a['family']}, {initials(a.get('given', ''))}".strip(", ")
    names = [one(a) for a in auth]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) <= 20:
        return ", ".join(names[:-1]) + ", & " + names[-1]
    return ", ".join(names[:19]) + ", . . . " + names[-1]


def to_apa(row: dict) -> str:
    t = item_type(row)
    auth = apa_authors(authors_of(row))
    y = year_of(row)
    title = (row.get("title") or "").rstrip(".")
    outlet = row.get("outlet") or ""
    doi = doi_of(row)
    link = f"https://doi.org/{doi}" if doi else (row.get("link") or "")
    vol = row.get("volume")
    vi = f"*{vol}*" + (f"({row['issue']})" if row.get("issue") else "") if vol else ""
    pages = row.get("pages")
    if t == "journalArticle":
        tail = ", ".join(p for p in (f"*{outlet}*" if outlet else "", vi, str(pages) if pages else "") if p)
        ref = f"{auth} ({y}). {title}. {tail}."
    elif t == "book":
        pub = row.get("publisher") or outlet
        ref = f"{auth} ({y}). *{title}*." + (f" {pub}." if pub else "")
    elif t == "bookSection":
        eds = row.get("editors") or []
        ed_names = ", ".join(f"{initials(n.get('given', ''))} {n.get('family', '')}".strip()
                             for n in (split_name(e) for e in eds) if n)
        ed = f"In {ed_names} ({'Eds.' if len(eds) > 1 else 'Ed.'}), " if eds else "In "
        book = row.get("book_title") or outlet
        pp = f" (pp. {pages})" if pages else ""
        pub = row.get("publisher") or ""
        ref = f"{auth} ({y}). {title}. {ed}*{book}*{pp}." + (f" {pub}." if pub else "")
    elif t == "report":
        pub = row.get("publisher") or outlet
        num = f" ({row['report_number']})" if row.get("report_number") else ""
        ref = f"{auth} ({y}). *{title}*{num}." + (f" {pub}." if pub and pub not in auth else "")
    elif t == "thesis":
        ref = f"{auth} ({y}). *{title}* [Doctoral dissertation, {row.get('publisher') or outlet}]."
    elif t == "conferencePaper":
        ref = f"{auth} ({y}). *{title}* [Conference paper]." + (f" {outlet}." if outlet else "")
    elif t in ("preprint", "manuscript"):
        ref = f"{auth} ({y}). *{title}* [{outlet or 'Working paper'}]."
    elif t == "dataset":
        pub = row.get("publisher") or outlet
        ref = f"{auth} ({y}). *{title}* [Data set]." + (f" {pub}." if pub else "")
    else:  # webpage, blogPost
        site = outlet or row.get("publisher") or ""
        ref = f"{auth} ({y}). *{title}*." + (f" {site}." if site and site not in auth else "")
    ref = re.sub(r"\s+", " ", ref).replace("..", ".").strip()
    return f"{ref} {link}".strip()


def sort_key(row: dict) -> str:
    auth = authors_of(row)
    fam = (auth[0].get("family") or auth[0].get("literal")) if auth else (row.get("title") or "")
    return f"{fam.lower()} {year_of(row)} {(row.get('title') or '').lower()}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("rows")
    p.add_argument("-o", "--out", required=True, help="output stem, e.g. topics/X/bibliography")
    p.add_argument("--title", default="Bibliography", help="heading of the APA list")
    args = p.parse_args(argv)

    rows = json.loads(Path(args.rows).read_text(encoding="utf-8"))
    refs = sorted((r for r in rows if r.get("category") in BIB_CATEGORIES and r.get("title")),
                  key=sort_key)
    used: set[str] = set()
    csl, bib, ris, apa = [], [], [], []
    for row in refs:
        key = cite_key(row, used)
        row["cite_key"] = key
        csl.append(to_csl(row, key))
        bib.append(to_bibtex(row, key))
        ris.append(to_ris(row))
        apa.append(to_apa(row))

    stem = Path(args.out)
    stem.parent.mkdir(parents=True, exist_ok=True)
    stem.with_suffix(".json").write_text(json.dumps(csl, ensure_ascii=False, indent=2), encoding="utf-8")
    stem.with_suffix(".bib").write_text("\n".join(bib), encoding="utf-8")
    stem.with_suffix(".ris").write_text("\n".join(ris), encoding="utf-8")
    md = [f"# {args.title}", "", f"{len(apa)} references, APA 7th edition, alphabetical.", ""]
    md += [x for line in apa for x in (line, "")]
    stem.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")
    Path(args.rows).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(refs)} references -> {stem}.json/.bib/.ris/.md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
