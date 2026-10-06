#!/usr/bin/env python3
"""Search open and licensed scholarly sources and return normalised JSON.

Standard library only. Each connector maps one API to a common record shape so the
search agents can merge, de-duplicate and rank results across sources.

Usage
-----
    python search_sources.py --list
    python search_sources.py -q "international alliance integration" -c books,articles -n 10
    python search_sources.py -q "differentiated integration alliance" -s openalex,crossref -o out.json
    python search_sources.py -q "alliance integration" -c people -n 25     # top authors on a topic

Credentials are read from environment variables, or from a .env file in the skill
directory or in ~/.config/academic-search/.env (see .env.example).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

SKILL_DIR = Path(__file__).resolve().parent.parent
TIMEOUT = 25
USER_AGENT = "academic-literature-search/1.0 (academic research)"

CATEGORIES = [
    "books", "articles", "unpublished", "reports", "data", "websites", "blogs",
    "events", "people",
]


# --------------------------------------------------------------------------- utils

def load_env() -> None:
    """Populate os.environ from .env files without overriding existing values."""
    for path in (SKILL_DIR / ".env", Path.home() / ".config" / "academic-search" / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def http(url: str, params: dict | None = None, headers: dict | None = None,
         data: dict | None = None, raw: bool = False):
    """GET (or POST JSON when data is given) and return parsed JSON or raw text."""
    if params:
        url = f"{url}{'&' if '?' in url else '?'}{urllib.parse.urlencode(params)}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method="POST" if body else "GET")
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json" if not raw else "*/*")
    if body:
        req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    return text if raw else json.loads(text)


def first(value, default=None):
    if isinstance(value, list):
        return value[0] if value else default
    return value if value is not None else default


def year_of(value) -> int | None:
    if value is None:
        return None
    text = str(value)
    digits = text[:4]
    return int(digits) if digits.isdigit() else None


def doi_url(doi: str | None) -> str | None:
    if not doi:
        return None
    doi = doi.replace("https://doi.org/", "").replace("http://dx.doi.org/", "")
    return f"https://doi.org/{doi}"


def short(text: str | None, limit: int = 400) -> str | None:
    if not text:
        return None
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def openalex_abstract(index: dict | None) -> str | None:
    if not index:
        return None
    words = sorted((pos, word) for word, positions in index.items() for pos in positions)
    return " ".join(word for _, word in words)


@dataclass
class Record:
    source: str
    category: str
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    publisher: str | None = None
    type: str | None = None
    url: str | None = None
    doi: str | None = None
    abstract: str | None = None
    citations: int | None = None
    open_access: bool | None = None
    access_note: str | None = None


@dataclass
class Connector:
    name: str
    description: str
    categories: list[str]
    needs: list[str]                       # env vars that must all be set
    func: Callable[[str, str, int], list[Record]]
    licensed: bool = False                 # True = WU-licensed / subscription source
    optional_env: list[str] = field(default_factory=list)

    def missing(self) -> list[str]:
        return [name for name in self.needs if not env(name)]


# ---------------------------------------------------------------------- connectors

OPENALEX_TYPES = {"books": "book|book-chapter", "articles": "article|review",
                  "unpublished": "preprint|dissertation", "reports": "report",
                  "data": "dataset"}


def search_openalex(query: str, category: str, n: int) -> list[Record]:
    params = {"search": query, "per-page": min(n, 200), "sort": "relevance_score:desc"}
    if category in OPENALEX_TYPES:
        params["filter"] = f"type:{OPENALEX_TYPES[category]}"
    if env("OPENALEX_EMAIL"):
        params["mailto"] = env("OPENALEX_EMAIL")
    if env("OPENALEX_API_KEY"):
        params["api_key"] = env("OPENALEX_API_KEY")
    out = []
    for w in http("https://api.openalex.org/works", params).get("results", []):
        loc = w.get("primary_location") or {}
        src = loc.get("source") or {}
        oa = w.get("open_access") or {}
        out.append(Record(
            source="openalex", category=category, title=w.get("display_name") or "",
            authors=[a["author"]["display_name"] for a in w.get("authorships", [])[:6]
                     if a.get("author")],
            year=w.get("publication_year"), venue=src.get("display_name"),
            publisher=src.get("host_organization_name"), type=w.get("type"),
            url=w.get("doi") or oa.get("oa_url") or w.get("id"),
            doi=(w.get("doi") or "").replace("https://doi.org/", "") or None,
            abstract=short(openalex_abstract(w.get("abstract_inverted_index"))),
            citations=w.get("cited_by_count"), open_access=oa.get("is_oa"),
            access_note=oa.get("oa_url"),
        ))
    return out


CROSSREF_TYPES = {"books": "book,book-chapter,monograph,edited-book", "articles": "journal-article",
                  "unpublished": "posted-content,dissertation", "reports": "report"}


def search_crossref(query: str, category: str, n: int) -> list[Record]:
    params = {"query": query, "rows": min(n, 100),
              "select": "DOI,title,author,issued,container-title,publisher,type,"
                        "is-referenced-by-count,URL,abstract"}
    if category in CROSSREF_TYPES:
        params["filter"] = ",".join(f"type:{t}" for t in CROSSREF_TYPES[category].split(","))
    if env("CROSSREF_EMAIL"):
        params["mailto"] = env("CROSSREF_EMAIL")
    out = []
    for it in http("https://api.crossref.org/works", params)["message"].get("items", []):
        authors = [" ".join(filter(None, [a.get("given"), a.get("family")]))
                   for a in it.get("author", [])[:6]]
        parts = (it.get("issued") or {}).get("date-parts") or [[None]]
        out.append(Record(
            source="crossref", category=category, title=first(it.get("title"), ""),
            authors=authors, year=first(parts[0]), venue=first(it.get("container-title")),
            publisher=it.get("publisher"), type=it.get("type"),
            url=doi_url(it.get("DOI")) or it.get("URL"), doi=it.get("DOI"),
            abstract=short(it.get("abstract")), citations=it.get("is-referenced-by-count"),
        ))
    return out


def search_semantic_scholar(query: str, category: str, n: int) -> list[Record]:
    headers = {"x-api-key": env("S2_API_KEY")} if env("S2_API_KEY") else {}
    params = {"query": query, "limit": min(n, 100),
              "fields": "title,authors,year,venue,externalIds,url,citationCount,"
                        "openAccessPdf,abstract,publicationTypes"}
    out = []
    for p in http("https://api.semanticscholar.org/graph/v1/paper/search",
                  params, headers).get("data", []) or []:
        doi = (p.get("externalIds") or {}).get("DOI")
        pdf = (p.get("openAccessPdf") or {}).get("url")
        out.append(Record(
            source="semantic_scholar", category=category, title=p.get("title") or "",
            authors=[a.get("name") for a in (p.get("authors") or [])[:6]],
            year=p.get("year"), venue=p.get("venue"),
            type=", ".join(p.get("publicationTypes") or []) or None,
            url=doi_url(doi) or p.get("url"), doi=doi, abstract=short(p.get("abstract")),
            citations=p.get("citationCount"), open_access=bool(pdf), access_note=pdf,
        ))
    return out


def search_core(query: str, category: str, n: int) -> list[Record]:
    headers = {"Authorization": f"Bearer {env('CORE_API_KEY')}"}
    data = http("https://api.core.ac.uk/v3/search/works",
                {"q": query, "limit": min(n, 100)}, headers)
    out = []
    for w in data.get("results", []):
        out.append(Record(
            source="core", category=category, title=w.get("title") or "",
            authors=[a.get("name") for a in (w.get("authors") or [])[:6]],
            year=w.get("yearPublished"), publisher=w.get("publisher"),
            type=first(w.get("documentType")),
            url=doi_url(w.get("doi")) or w.get("downloadUrl"), doi=w.get("doi"),
            abstract=short(w.get("abstract")), citations=w.get("citationCount"),
            open_access=True, access_note=w.get("downloadUrl"),
        ))
    return out


def search_doaj(query: str, category: str, n: int) -> list[Record]:
    url = "https://doaj.org/api/search/articles/" + urllib.parse.quote(query)
    out = []
    for r in http(url, {"pageSize": min(n, 100)}).get("results", []):
        b = r.get("bibjson", {})
        doi = next((i.get("id") for i in b.get("identifier", []) if i.get("type") == "doi"),
                   None)
        link = next((l.get("url") for l in b.get("link", [])), None)
        out.append(Record(
            source="doaj", category=category, title=b.get("title") or "",
            authors=[a.get("name") for a in b.get("author", [])[:6]],
            year=year_of(b.get("year")), venue=(b.get("journal") or {}).get("title"),
            publisher=(b.get("journal") or {}).get("publisher"), type="journal-article",
            url=doi_url(doi) or link, doi=doi, abstract=short(b.get("abstract")),
            open_access=True,
        ))
    return out


def search_arxiv(query: str, category: str, n: int) -> list[Record]:
    text = http("https://export.arxiv.org/api/query",
                {"search_query": f"all:{query}", "max_results": min(n, 100),
                 "sortBy": "relevance"}, raw=True)
    ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
    out = []
    for e in ET.fromstring(text).findall("a:entry", ns):
        doi = e.findtext("x:doi", default=None, namespaces=ns)
        out.append(Record(
            source="arxiv", category=category,
            title=" ".join((e.findtext("a:title", "", ns)).split()),
            authors=[a.findtext("a:name", "", ns) for a in e.findall("a:author", ns)][:6],
            year=year_of(e.findtext("a:published", None, ns)), venue="arXiv",
            type="preprint", url=e.findtext("a:id", None, ns), doi=doi,
            abstract=short(e.findtext("a:summary", None, ns)), open_access=True,
        ))
    return out


def search_openlibrary(query: str, category: str, n: int) -> list[Record]:
    data = http("https://openlibrary.org/search.json",
                {"q": query, "limit": min(n, 100),
                 "fields": "key,title,author_name,first_publish_year,publisher,isbn,"
                           "edition_count,ebook_access"})
    out = []
    for d in data.get("docs", []):
        out.append(Record(
            source="openlibrary", category=category, title=d.get("title") or "",
            authors=(d.get("author_name") or [])[:6], year=d.get("first_publish_year"),
            publisher=first(d.get("publisher")), type="book",
            url=f"https://openlibrary.org{d['key']}" if d.get("key") else None,
            open_access=d.get("ebook_access") == "public",
            access_note=f"ISBN {first(d.get('isbn'))}" if d.get("isbn") else None,
        ))
    return out


def search_google_books(query: str, category: str, n: int) -> list[Record]:
    params = {"q": query, "maxResults": min(n, 40), "printType": "books",
              "orderBy": "relevance"}
    if env("GOOGLE_API_KEY"):
        params["key"] = env("GOOGLE_API_KEY")
    out = []
    for it in http("https://www.googleapis.com/books/v1/volumes", params).get("items", []):
        v = it.get("volumeInfo", {})
        isbn = next((i["identifier"] for i in v.get("industryIdentifiers", [])
                     if i.get("type") == "ISBN_13"), None)
        out.append(Record(
            source="google_books", category=category,
            title=": ".join(filter(None, [v.get("title"), v.get("subtitle")])),
            authors=(v.get("authors") or [])[:6], year=year_of(v.get("publishedDate")),
            publisher=v.get("publisher"), type="book",
            url=v.get("infoLink") or v.get("canonicalVolumeLink"),
            abstract=short(v.get("description")),
            access_note=f"ISBN {isbn}" if isbn else None,
        ))
    return out


SPRINGER_TYPES = {"books": "Book", "articles": "Journal"}


def search_springer(query: str, category: str, n: int) -> list[Record]:
    q = query if category not in SPRINGER_TYPES else f"{query} type:{SPRINGER_TYPES[category]}"
    data = http("https://api.springernature.com/meta/v2/json",
                {"q": q, "p": min(n, 50), "api_key": env("SPRINGER_API_KEY")})
    out = []
    for r in data.get("records", []):
        html = next((u.get("value") for u in r.get("url", []) if u.get("format") == "html"),
                    None)
        out.append(Record(
            source="springer", category=category, title=r.get("title") or "",
            authors=[c.get("creator") for c in r.get("creators", [])[:6]],
            year=year_of(r.get("publicationDate")), venue=r.get("publicationName"),
            publisher=r.get("publisher"), type=r.get("contentType"),
            url=doi_url(r.get("doi")) or html, doi=r.get("doi"),
            abstract=short(r.get("abstract") if isinstance(r.get("abstract"), str) else None),
            open_access=str(r.get("openaccess")).lower() == "true",
            access_note="SpringerLink (WU licence likely)",
        ))
    return out


def search_scopus(query: str, category: str, n: int) -> list[Record]:
    headers = {"X-ELS-APIKey": env("ELSEVIER_API_KEY")}
    if env("ELSEVIER_INSTTOKEN"):
        headers["X-ELS-Insttoken"] = env("ELSEVIER_INSTTOKEN")
    doctype = {"books": " AND DOCTYPE(bk OR ch)", "articles": " AND DOCTYPE(ar OR re)",
               "unpublished": " AND DOCTYPE(cp OR dp)"}
    data = http("https://api.elsevier.com/content/search/scopus",
                {"query": f"TITLE-ABS-KEY({query}){doctype.get(category, '')}",
                 "count": min(n, 25), "sort": "relevancy"}, headers)
    out = []
    for e in data.get("search-results", {}).get("entry", []):
        if "error" in e:
            continue
        link = next((l.get("@href") for l in e.get("link", []) if l.get("@ref") == "scopus"),
                    None)
        cites = e.get("citedby-count")
        out.append(Record(
            source="scopus", category=category, title=e.get("dc:title") or "",
            authors=[e["dc:creator"]] if e.get("dc:creator") else [],
            year=year_of(e.get("prism:coverDate")), venue=e.get("prism:publicationName"),
            type=e.get("subtypeDescription"), url=doi_url(e.get("prism:doi")) or link,
            doi=e.get("prism:doi"), citations=int(cites) if str(cites).isdigit() else None,
            open_access=e.get("openaccessFlag"), access_note="Scopus (WU licence)",
        ))
    return out


def search_wos(query: str, category: str, n: int) -> list[Record]:
    data = http("https://api.clarivate.com/apis/wos-starter/v1/documents",
                {"q": f"TS=({query})", "limit": min(n, 50), "db": "WOS",
                 "sortField": "RS+D"},
                {"X-ApiKey": env("CLARIVATE_WOS_API_KEY")})
    out = []
    for h in data.get("hits", []):
        src = h.get("source", {})
        ids = h.get("identifiers", {})
        cites = next((c.get("count") for c in h.get("citations", [])), None)
        out.append(Record(
            source="web_of_science", category=category, title=h.get("title") or "",
            authors=[a.get("displayName") for a in
                     (h.get("names", {}).get("authors") or [])[:6]],
            year=src.get("publishYear"), venue=src.get("sourceTitle"),
            type=first(h.get("types")), url=doi_url(ids.get("doi")) or
            (h.get("links") or {}).get("record"), doi=ids.get("doi"), citations=cites,
            access_note="Web of Science (WU licence)",
        ))
    return out


def search_primo(query: str, category: str, n: int) -> list[Record]:
    """WU library catalogue (Ex Libris Primo VE). Needs a key issued by the library."""
    host = env("PRIMO_API_HOST") or "https://api-eu.hosted.exlibrisgroup.com"
    params = {"vid": env("PRIMO_VID"), "tab": env("PRIMO_TAB") or "Everything",
              "scope": env("PRIMO_SCOPE") or "MyInst_and_CI",
              "q": f"any,contains,{query}", "limit": min(n, 50),
              "apikey": env("PRIMO_API_KEY")}
    if category == "books":
        params["qInclude"] = "facet_rtype,exact,books"
    elif category == "articles":
        params["qInclude"] = "facet_rtype,exact,articles"
    elif category == "unpublished":
        params["qInclude"] = "facet_rtype,exact,dissertations"
    data = http(f"{host}/primo/v1/search", params)
    base = env("PRIMO_DISCOVERY_BASE")
    out = []
    for d in data.get("docs", []):
        disp = d.get("pnx", {}).get("display", {})
        rec_id = first(d.get("pnx", {}).get("control", {}).get("recordid"))
        url = (f"{base}/discovery/fulldisplay?docid={rec_id}&vid={params['vid']}"
               if base and rec_id else None)
        out.append(Record(
            source="wu_primo", category=category, title=first(disp.get("title"), ""),
            authors=(disp.get("creator") or disp.get("contributor") or [])[:6],
            year=year_of(first(disp.get("creationdate"))), publisher=first(disp.get("publisher")),
            type=first(disp.get("type")), url=url, abstract=short(first(disp.get("description"))),
            access_note="WU Bibliothek catalogue",
        ))
    return out


def search_ebsco_eds(query: str, category: str, n: int) -> list[Record]:
    """EBSCO Discovery Service (Business Source etc.). Untested: needs WU EDS API profile."""
    base = "https://eds-api.ebscohost.com"
    auth = http(f"{base}/authservice/rest/uidauth",
                data={"UserId": env("EDS_USER"), "Password": env("EDS_PASSWORD"),
                      "InterfaceId": "academic-search"})
    token = auth["AuthToken"]
    session = http(f"{base}/edsapi/rest/createsession",
                   {"profile": env("EDS_PROFILE"), "guest": "n"},
                   {"x-authenticationToken": token})["SessionToken"]
    data = http(f"{base}/edsapi/rest/search",
                {"query": query, "resultsperpage": min(n, 100), "view": "brief",
                 "highlight": "n"},
                {"x-authenticationToken": token, "x-sessionToken": session})
    out = []
    for r in data.get("SearchResult", {}).get("Data", {}).get("Records", []) or []:
        bib = r.get("RecordInfo", {}).get("BibRecord", {})
        ent = bib.get("BibEntity", {})
        rel = bib.get("BibRelationships", {})
        title = first([t.get("TitleFull") for t in ent.get("Titles", [])], "")
        authors = [c.get("PersonEntity", {}).get("Name", {}).get("NameFull")
                   for c in rel.get("HasContributorRelationships", [])[:6]]
        doi = next((i.get("Value") for i in ent.get("Identifiers", [])
                    if i.get("Type") == "doi"), None)
        out.append(Record(
            source="ebsco_eds", category=category, title=title,
            authors=[a for a in authors if a], type=r.get("Header", {}).get("PubType"),
            url=doi_url(doi) or r.get("PLink"), doi=doi,
            access_note="EBSCO (WU licence)",
        ))
    return out


def search_github(query: str, category: str, n: int) -> list[Record]:
    headers = {"Accept": "application/vnd.github+json"}
    if env("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {env('GITHUB_TOKEN')}"
    data = http("https://api.github.com/search/repositories",
                {"q": query, "sort": "stars", "order": "desc", "per_page": min(n, 100)},
                headers)
    out = []
    for r in data.get("items", []):
        out.append(Record(
            source="github", category=category, title=r.get("full_name") or "",
            authors=[r.get("owner", {}).get("login")], year=year_of(r.get("pushed_at")),
            venue="GitHub", type=f"repository ({r.get('language') or 'n/a'})",
            url=r.get("html_url"), abstract=short(r.get("description")),
            citations=r.get("stargazers_count"), open_access=True,
            access_note=f"{r.get('stargazers_count')} stars; last push {r.get('pushed_at', '')[:10]}; "
                        f"licence {(r.get('license') or {}).get('spdx_id', 'none')}",
        ))
    return out


def search_zenodo(query: str, category: str, n: int) -> list[Record]:
    q = f"({query}) AND resource_type.type:dataset" if category == "data" else (
        f"({query}) AND resource_type.type:publication" if category == "unpublished" else query)
    data = http("https://zenodo.org/api/records", {"q": q, "size": min(n, 100),
                                                   "sort": "bestmatch"})
    out = []
    for h in data.get("hits", {}).get("hits", []):
        m = h.get("metadata", {})
        out.append(Record(
            source="zenodo", category=category, title=m.get("title") or "",
            authors=[c.get("name") for c in m.get("creators", [])[:6]],
            year=year_of(m.get("publication_date")), venue="Zenodo",
            type=(m.get("resource_type") or {}).get("type"),
            url=(h.get("links") or {}).get("self_html") or doi_url(h.get("doi")),
            doi=h.get("doi"), abstract=short(m.get("description")), open_access=True,
            access_note=(m.get("license") or {}).get("id"),
        ))
    return out


def search_dataverse(query: str, category: str, n: int) -> list[Record]:
    data = http("https://dataverse.harvard.edu/api/search",
                {"q": query, "type": "dataset", "per_page": min(n, 100)})
    out = []
    for it in data.get("data", {}).get("items", []):
        out.append(Record(
            source="harvard_dataverse", category=category, title=it.get("name") or "",
            authors=(it.get("authors") or [])[:6], year=year_of(it.get("published_at")),
            venue="Harvard Dataverse", publisher=it.get("publisher"), type="dataset",
            url=it.get("url"), doi=(it.get("global_id") or "").replace("doi:", "") or None,
            abstract=short(it.get("description")), open_access=True,
        ))
    return out


def search_kaggle(query: str, category: str, n: int) -> list[Record]:
    token = base64.b64encode(f"{env('KAGGLE_USERNAME')}:{env('KAGGLE_KEY')}".encode()).decode()
    data = http("https://www.kaggle.com/api/v1/datasets/list",
                {"search": query, "sortBy": "votes", "page": 1},
                {"Authorization": f"Basic {token}"})
    out = []
    for d in (data if isinstance(data, list) else [])[:n]:
        out.append(Record(
            source="kaggle", category=category, title=d.get("title") or "",
            authors=[d.get("creatorName") or d.get("ownerName") or ""],
            year=year_of(d.get("lastUpdated")), venue="Kaggle", type="dataset",
            url=d.get("url") or f"https://www.kaggle.com/datasets/{d.get('ref')}",
            abstract=short(d.get("subtitle")), citations=d.get("voteCount"),
            open_access=True, access_note=f"licence {d.get('licenseName', 'see page')}; "
                                          f"usability {d.get('usabilityRating')}",
        ))
    return out


def search_data_europa(query: str, category: str, n: int) -> list[Record]:
    data = http("https://data.europa.eu/api/hub/search/search",
                {"q": query, "filter": "dataset", "limit": min(n, 100)})
    out = []
    for r in data.get("result", {}).get("results", []):
        title = r.get("title") or {}
        desc = r.get("description") or {}
        out.append(Record(
            source="data_europa", category=category,
            title=title.get("en") or first(list(title.values()), ""),
            authors=[(r.get("publisher") or {}).get("name") or ""],
            year=year_of(r.get("modified") or r.get("issued")), venue="data.europa.eu",
            type="dataset", url=f"https://data.europa.eu/data/datasets/{r.get('id')}",
            abstract=short(desc.get("en") or first(list(desc.values()))), open_access=True,
        ))
    return out


def search_data_gov(query: str, category: str, n: int) -> list[Record]:
    data = http("https://catalog.data.gov/api/3/action/package_search",
                {"q": query, "rows": min(n, 100)})
    out = []
    for r in data.get("result", {}).get("results", []):
        out.append(Record(
            source="data_gov", category=category, title=r.get("title") or "",
            authors=[(r.get("organization") or {}).get("title") or ""],
            year=year_of(r.get("metadata_modified")), venue="data.gov", type="dataset",
            url=f"https://catalog.data.gov/dataset/{r.get('name')}",
            abstract=short(r.get("notes")), open_access=True,
        ))
    return out



def search_openalex_people(query: str, category: str, n: int) -> list[Record]:
    """Most productive authors on the topic: OpenAlex works grouped by author, then
    author details (affiliation, works, citations) in one follow-up call."""
    params = {"search": query, "group_by": "authorships.author.id", "per-page": 200}
    if env("OPENALEX_EMAIL"):
        params["mailto"] = env("OPENALEX_EMAIL")
    groups = http("https://api.openalex.org/works", params).get("group_by", [])
    groups = [g for g in groups if g.get("key", "").startswith("https://openalex.org/A")][:n]
    if not groups:
        return []
    ids = "|".join(g["key"].rsplit("/", 1)[-1] for g in groups)
    details = {a["id"]: a for a in http("https://api.openalex.org/authors",
                                        {"filter": f"ids.openalex:{ids}", "per-page": 100}
                                        ).get("results", [])}
    out = []
    for g in groups:
        a = details.get(g["key"], {})
        inst = (a.get("last_known_institutions") or [{}])[0]
        orcid = a.get("orcid")
        out.append(Record(
            source="openalex", category="people", title=g.get("key_display_name") or "",
            authors=[g.get("key_display_name") or ""], venue=inst.get("display_name"),
            publisher=inst.get("country_code"), type="author",
            url=orcid or a.get("id") or g["key"],
            abstract=f"{g.get('count')} works matching the query; {a.get('works_count')} works "
                     f"and {a.get('cited_by_count')} citations in total",
            citations=g.get("count"),
            access_note="; ".join(t.get("display_name", "") for t in (a.get("topics") or [])[:3]),
        ))
    return out


def search_osf(query: str, category: str, n: int) -> list[Record]:
    """OSF Preprints (SocArXiv, PsyArXiv, MetaArXiv and others)."""
    data = http("https://api.osf.io/v2/search/preprints/", {"q": query, "page[size]": min(n, 100)})
    out = []
    for p in data.get("data", []):
        at = p.get("attributes", {})
        doi = at.get("doi") or (at.get("article_doi") or None)
        out.append(Record(
            source="osf", category=category, title=at.get("title") or "",
            year=year_of(at.get("date_published")), venue="OSF Preprints", type="preprint",
            url=doi_url(doi) or (p.get("links") or {}).get("html"), doi=doi,
            abstract=short(at.get("description")), open_access=True,
        ))
    return out


def search_worldbank_docs(query: str, category: str, n: int) -> list[Record]:
    """World Bank Documents & Reports (policy research working papers, reports)."""
    data = http("https://search.worldbank.org/api/v2/wds",
                {"format": "json", "qterm": query, "rows": min(n, 100), "fl": "docna,docdt,"
                 "docty,url,repnb,abstracts,authr,count"})
    out = []
    for d in (data.get("documents") or {}).values():
        if not isinstance(d, dict) or not d.get("docna"):
            continue
        out.append(Record(
            source="worldbank", category=category, title=d.get("docna") or "",
            authors=[d.get("authr")] if d.get("authr") else [], year=year_of(d.get("docdt")),
            venue="World Bank Documents & Reports", publisher="World Bank", type=d.get("docty"),
            url=d.get("url"), abstract=short((d.get("abstracts") or {}).get("cdata!")
                                            if isinstance(d.get("abstracts"), dict) else None),
            open_access=True, access_note=d.get("repnb"),
        ))
    return out


CONNECTORS: dict[str, Connector] = {c.name: c for c in [
    Connector("openalex", "OpenAlex: 250M+ works, books, chapters, preprints, reports, datasets",
              ["books", "articles", "unpublished", "reports", "data"], [], search_openalex,
              optional_env=["OPENALEX_EMAIL", "OPENALEX_API_KEY"]),
    Connector("openalex_people", "OpenAlex: most productive authors on the topic (works grouped by author)",
              ["people"], [], search_openalex_people, optional_env=["OPENALEX_EMAIL"]),
    Connector("crossref", "Crossref: DOI metadata for articles, books, chapters, preprints, reports",
              ["books", "articles", "unpublished", "reports"], [], search_crossref,
              optional_env=["CROSSREF_EMAIL"]),
    Connector("semantic_scholar", "Semantic Scholar: articles and preprints with citation counts",
              ["articles", "unpublished"], [], search_semantic_scholar, optional_env=["S2_API_KEY"]),
    Connector("core", "CORE: open-access full texts, working papers, theses, reports",
              ["articles", "unpublished", "reports"], ["CORE_API_KEY"], search_core),
    Connector("doaj", "DOAJ: open-access journal articles", ["articles"], [], search_doaj),
    Connector("arxiv", "arXiv: preprints (econ, q-fin, stat, cs)", ["unpublished"], [],
              search_arxiv),
    Connector("osf", "OSF Preprints: SocArXiv, PsyArXiv, MetaArXiv and others", ["unpublished"], [],
              search_osf),
    Connector("worldbank", "World Bank Documents & Reports: working papers and reports",
              ["reports", "unpublished"], [], search_worldbank_docs),
    Connector("openlibrary", "Open Library: book metadata", ["books"], [], search_openlibrary),
    Connector("google_books", "Google Books: book metadata and descriptions", ["books"], [],
              search_google_books, optional_env=["GOOGLE_API_KEY"]),
    Connector("springer", "Springer Nature: books, chapters and journals (SpringerLink)",
              ["books", "articles"], ["SPRINGER_API_KEY"], search_springer, licensed=True),
    Connector("scopus", "Elsevier Scopus: abstracts and citations",
              ["books", "articles", "unpublished"], ["ELSEVIER_API_KEY"], search_scopus, licensed=True,
              optional_env=["ELSEVIER_INSTTOKEN"]),
    Connector("wos", "Clarivate Web of Science Starter API",
              ["articles"], ["CLARIVATE_WOS_API_KEY"], search_wos, licensed=True),
    Connector("wu_primo", "WU Bibliothek catalogue (Ex Libris Primo VE)",
              ["books", "articles", "unpublished", "reports"], ["PRIMO_API_KEY", "PRIMO_VID"],
              search_primo, licensed=True,
              optional_env=["PRIMO_API_HOST", "PRIMO_TAB", "PRIMO_SCOPE",
                            "PRIMO_DISCOVERY_BASE"]),
    Connector("ebsco_eds", "EBSCO Discovery Service (Business Source Ultimate etc.)",
              ["articles", "reports"], ["EDS_USER", "EDS_PASSWORD", "EDS_PROFILE"],
              search_ebsco_eds, licensed=True),
    Connector("github", "GitHub: repositories (replication code, datasets)",
              ["data"], [], search_github,
              optional_env=["GITHUB_TOKEN"]),
    Connector("zenodo", "Zenodo: datasets, replication packages, working papers",
              ["data", "unpublished"], [], search_zenodo),
    Connector("harvard_dataverse", "Harvard Dataverse: research datasets", ["data"], [],
              search_dataverse),
    Connector("kaggle", "Kaggle: datasets", ["data"], ["KAGGLE_USERNAME", "KAGGLE_KEY"],
              search_kaggle),
    Connector("data_europa", "data.europa.eu: EU open data portal", ["data"], [],
              search_data_europa),
    Connector("data_gov", "data.gov: US open data catalogue", ["data"], [], search_data_gov),
]}


# ---------------------------------------------------------------------------- main

def dedupe(records: list[Record]) -> list[Record]:
    seen: dict[str, Record] = {}
    for r in records:
        key = (r.doi or "").lower() or " ".join(r.title.lower().split())[:120]
        if not key:
            continue
        if key in seen:
            kept = seen[key]
            kept.citations = max(filter(None, [kept.citations, r.citations]), default=None)
            if r.source not in kept.source.split("+"):
                kept.source += f"+{r.source}"
        else:
            seen[key] = r
    return list(seen.values())


def run(query: str, categories: list[str], sources: list[str] | None, n: int) -> dict:
    results: list[Record] = []
    meta = {"query": query, "categories": categories, "ran": [], "skipped": {}, "errors": {}}
    for cat in categories:
        for c in CONNECTORS.values():
            if cat not in c.categories or (sources and c.name not in sources):
                continue
            label = f"{c.name}:{cat}"
            if c.missing():
                meta["skipped"][label] = "missing " + ", ".join(c.missing())
                continue
            try:
                found = c.func(query, cat, n)
                results.extend(found)
                meta["ran"].append(f"{label} ({len(found)})")
            except urllib.error.HTTPError as e:
                meta["errors"][label] = f"HTTP {e.code} {e.reason}"
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                meta["errors"][label] = f"network: {getattr(e, 'reason', e)}"
            except (ValueError, KeyError, ET.ParseError) as e:
                meta["errors"][label] = f"parse: {e!r}"
    merged = dedupe(results)
    meta["total"] = len(merged)
    return {"meta": meta, "results": [asdict(r) for r in merged]}


def list_connectors() -> None:
    print(f"{'connector':<18} {'status':<10} {'licensed':<9} categories / notes")
    for c in CONNECTORS.values():
        missing = c.missing()
        status = "ready" if not missing else "no key"
        note = f"needs {', '.join(missing)}" if missing else c.description
        print(f"{c.name:<18} {status:<10} {'yes' if c.licensed else 'no':<9} "
              f"{','.join(c.categories)} | {note}")


def main(argv: list[str] | None = None) -> int:
    load_env()
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-q", "--query", help="search query (English keywords work best)")
    p.add_argument("-c", "--categories", default=",".join(CATEGORIES),
                   help="comma-separated: " + ",".join(CATEGORIES))
    p.add_argument("-s", "--sources", help="restrict to these connectors (comma-separated)")
    p.add_argument("-n", "--limit", type=int, default=10, help="results per connector")
    p.add_argument("-o", "--out", help="write JSON here instead of stdout")
    p.add_argument("--list", action="store_true", help="show connectors and key status")
    args = p.parse_args(argv)

    if args.list:
        list_connectors()
        return 0
    if not args.query:
        p.error("--query is required unless --list is given")
    cats = [c.strip() for c in args.categories.split(",") if c.strip()]
    unknown = set(cats) - set(CATEGORIES)
    if unknown:
        p.error(f"unknown categories: {', '.join(sorted(unknown))}")
    sources = [s.strip() for s in args.sources.split(",")] if args.sources else None
    if sources and set(sources) - set(CONNECTORS):
        p.error(f"unknown sources: {', '.join(sorted(set(sources) - set(CONNECTORS)))}")

    payload = run(args.query, cats, sources, args.limit)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        m = payload["meta"]
        print(f"{m['total']} records -> {args.out}; ran {len(m['ran'])}, "
              f"skipped {len(m['skipped'])}, errors {len(m['errors'])}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
