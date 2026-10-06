#!/usr/bin/env python3
"""Render reproducible Boolean search strings for EBSCO, Web of Science, Scopus and others
from a concept file, so the researcher can re-run the search in the licensed databases.

Input (JSON written by the agent after reading the research question):
{
  "topic": "Differentiated International Integration in International Alliances",
  "years": [2010, 2026],                       # optional publication-year window
  "concepts": [                                # one block per concept, joined with AND
    {"name": "alliance", "terms": ["international alliance*", "strategic alliance*",
                                   "international joint venture*", "cross-border alliance*"]},
    {"name": "integration", "terms": ["integration", "coordination", "control",
                                      "autonomy", "\"differentiat* integration\""]}
  ],
  "exclude": ["education", "nursing"],          # optional NOT terms
  "subjects": ["international business", "strategic management"]   # optional, EBSCO SU
}

Output: JSON {database: {"query": ..., "note": ...}} for build_output.py --search-strings,
and a readable Markdown rendering on stdout.

Usage:
    python search_strings.py concepts.json -o topics/<topic>/search_strings.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def quote(term: str) -> str:
    term = term.strip().strip('"')
    return f'"{term}"' if " " in term else term


def block(terms: list[str], wrapper=lambda t: t) -> str:
    return "(" + " OR ".join(wrapper(quote(t)) for t in terms) + ")"


def ebsco(spec: dict) -> dict:
    # Business Source: field codes TI (title), AB (abstract), SU (subject); * truncation;
    # phrases in quotes; W# / N# proximity. One TI/AB/SU block per concept, AND between.
    parts = []
    for c in spec["concepts"]:
        inner = " OR ".join(quote(t) for t in c["terms"])
        parts.append(f"(TI ({inner}) OR AB ({inner}) OR SU ({inner}))")
    q = "\nAND\n".join(parts)
    if spec.get("exclude"):
        q += "\nNOT\n(TI (" + " OR ".join(quote(t) for t in spec["exclude"]) + ") OR SU (" + \
             " OR ".join(quote(t) for t in spec["exclude"]) + "))"
    note = "Business Source Premier/Ultimate via WU library. Paste into Advanced Search as one " \
           "line (or one block per row with AND). Limiters: Scholarly (Peer Reviewed) Journals"
    if spec.get("years"):
        note += f", Published Date {spec['years'][0]}-{spec['years'][1]}"
    note += ". EBSCO ignores the line breaks."
    return {"query": q, "note": note}


def wos(spec: dict) -> dict:
    # Web of Science Core Collection advanced search: TS = topic (title, abstract, author
    # keywords, Keywords Plus); * truncation; NEAR/x proximity; PY= year range.
    parts = [f"TS={block(c['terms'])}" for c in spec["concepts"]]
    q = " AND ".join(parts)
    if spec.get("exclude"):
        q += f" NOT TS={block(spec['exclude'])}"
    if spec.get("years"):
        q += f" AND PY=({spec['years'][0]}-{spec['years'][1]})"
    q = q.replace(" AND ", "\nAND ").replace(" NOT ", "\nNOT ")
    return {"query": q, "note": "Web of Science Core Collection, Advanced Search. Refine by "
                                "Document Types: Article, Review Article, Early Access; "
                                "WoS Categories: Business, Management."}


def scopus(spec: dict) -> dict:
    parts = [f"TITLE-ABS-KEY{block(c['terms'])}" for c in spec["concepts"]]
    q = " AND ".join(parts)
    if spec.get("exclude"):
        q += f" AND NOT TITLE-ABS-KEY{block(spec['exclude'])}"
    if spec.get("years"):
        q += f" AND PUBYEAR > {spec['years'][0] - 1} AND PUBYEAR < {spec['years'][1] + 1}"
    q += ' AND (LIMIT-TO(SUBJAREA, "BUSI") OR LIMIT-TO(SUBJAREA, "ECON") OR LIMIT-TO(SUBJAREA, "SOCI"))'
    q = q.replace(" AND ", "\nAND ")
    return {"query": q, "note": "Scopus Advanced Search (WU licence). Drop the SUBJAREA line for "
                                "a broader sweep."}


def google_scholar(spec: dict) -> dict:
    # Scholar: no truncation, short strings; use the two or three most distinctive terms
    terms = []
    for c in spec["concepts"]:
        clean = [re.sub(r"\*", "", t).strip('"') for t in c["terms"][:3]]
        terms.append("(" + " OR ".join(f'"{t}"' if " " in t else t for t in clean) + ")")
    return {"query": " ".join(terms), "note": "Google Scholar (and Semantic Scholar / Consensus): "
                                             "short form, no truncation. Sort by relevance, then "
                                             "by date for the last three years."}


def openalex(spec: dict) -> dict:
    terms = [t.replace("*", "").strip('"') for c in spec["concepts"] for t in c["terms"][:2]]
    return {"query": " ".join(terms), "note": "Plain-text query for OpenAlex, Crossref and "
                                             "Semantic Scholar (search_sources.py -q)."}


def primo(spec: dict) -> dict:
    parts = [block(c["terms"]) for c in spec["concepts"]]
    return {"query": " AND ".join(parts), "note": "WU CatalogPLUS / Primo advanced search "
                                                 "(any field contains). Filter: Resource type."}


def render_markdown(strings: dict) -> str:
    out = []
    for name, s in strings.items():
        out += [f"**{name}** – {s['note']}", "```", s["query"], "```", ""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("concepts", help="JSON concept file (see docstring)")
    p.add_argument("-o", "--out", help="write {database: {query, note}} JSON here")
    args = p.parse_args(argv)
    spec = json.loads(Path(args.concepts).read_text(encoding="utf-8"))
    if not spec.get("concepts"):
        p.error("concepts list is empty")
    strings = {
        "EBSCO Business Source": ebsco(spec),
        "Web of Science": wos(spec),
        "Scopus": scopus(spec),
        "WU CatalogPLUS (Primo)": primo(spec),
        "Google Scholar": google_scholar(spec),
        "OpenAlex / Crossref / Semantic Scholar": openalex(spec),
    }
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(strings, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    print(render_markdown(strings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
