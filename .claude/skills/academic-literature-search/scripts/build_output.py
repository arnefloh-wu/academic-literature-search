#!/usr/bin/env python3
"""Render curated rows as Notion-flavoured Markdown and as GitHub Markdown.

Layout of a topic page:
    ## Sources on <topic> (agent search, <D Month YYYY>)
    <intro paragraph>
    ### Synthesis                      (optional, from --synthesis, Notion markdown as is)
    ### Search strings                 (optional, from --search-strings JSON, as code blocks)
    ### Books & Book Chapters (n)      one H3 + table per category, eight columns:
        Category | Title | Authors / Source / Year | Outlet / Rank | Link | Key content |
        Relevance for the research question | Status

Usage:
    python build_output.py rows.json --topic "<topic>" --intro "..." \
        [--synthesis synthesis.md] [--search-strings search_strings.json] \
        --notion out/notion.md --markdown out/README.md [--date 2026-10-06]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

# key -> (section heading, value of the "Category" column)
CATEGORIES = {
    "books": ("Books & Book Chapters", "Book / Chapter"),
    "articles": ("Journal Articles", "Journal Article"),
    "unpublished": ("Working Papers & Unpublished Materials", "Unpublished"),
    "reports": ("Reports", "Report"),
    "data": ("Data", "Data"),
    "websites": ("Websites", "Website"),
    "blogs": ("Blogs", "Blog"),
    "events": ("Events & Calls", "Event / Call"),
    "people": ("People", "Person"),
}
ALIASES = {label.lower(): key for key, pair in CATEGORIES.items() for label in pair}
ALIASES.update({"book": "books", "book chapter": "books", "chapter": "books",
                "article": "articles", "journal article": "articles", "paper": "articles",
                "working paper": "unpublished", "working papers": "unpublished",
                "preprint": "unpublished", "conference paper": "unpublished",
                "dissertation": "unpublished", "thesis": "unpublished",
                "report": "reports", "dataset": "data", "datasets": "data",
                "website": "websites", "blog": "blogs", "event": "events",
                "conference": "events", "special issue": "events", "person": "people",
                "researcher": "people", "researchers": "people", "experts": "people"})
COLUMNS = ["Category", "Title", "Authors / Source / Year", "Outlet / Rank", "Link",
           "Key content", "Relevance for the research question", "Status"]
URL_RE = re.compile(r"https?://[^\s)\]>]+")
NOTION_SPECIAL = re.compile(r"([\\*~`$\[\]<>{}|^])")
DEFAULT_STATUS = "new; link unverified"


def category_key(value: str) -> str:
    key = (value or "").strip()
    if key in CATEGORIES:
        return key
    try:
        return ALIASES[key.lower()]
    except KeyError:
        raise SystemExit(f"unknown category {value!r}; use one of {', '.join(CATEGORIES)}")


def long_date(day: dt.date) -> str:
    return f"{day.day} {day.strftime('%B %Y')}"


def notion_text(text: str | None) -> str:
    """Escape Notion specials and turn bare URLs into links."""
    text = " ".join(str(text or "").split())
    parts, pos = [], 0
    for m in URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;")
        parts.append(NOTION_SPECIAL.sub(r"\\\1", text[pos:m.start()]))
        parts.append(f"[{NOTION_SPECIAL.sub(r'\\\1', url)}]({url})")
        pos = m.start() + len(url)
    parts.append(NOTION_SPECIAL.sub(r"\\\1", text[pos:]))
    return "".join(parts)


def notion_link(link: str | None) -> str:
    url = (URL_RE.search(link or "") or [None])[0] if link else None
    return notion_text(url) if url else notion_text(link)


def gfm_text(text: str | None) -> str:
    text = " ".join(str(text or "").split()).replace("|", "\\|")
    return URL_RE.sub(lambda m: f"<{m.group(0).rstrip('.,;')}>", text)


def group(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {key: [] for key in CATEGORIES}
    for row in rows:
        grouped[category_key(row.get("category", ""))].append(row)
    return grouped


def outlet_rank(row: dict) -> str:
    outlet, rank = (row.get("outlet") or "").strip(), (row.get("rank") or "").strip()
    return "; ".join(p for p in (outlet, rank) if p)


def cells(row: dict, key: str) -> list[str]:
    return [CATEGORIES[key][1], row.get("title"), row.get("author_source"), outlet_rank(row),
            row.get("link"), row.get("note"), row.get("relevance"),
            row.get("status") or DEFAULT_STATUS]


def heading(topic: str, day: dt.date) -> str:
    return f"Sources on {topic} (agent search, {long_date(day)})"


def search_strings_blocks(strings: dict | None, notion: bool) -> list[str]:
    """Render {"EBSCO Business Source": "...", "Web of Science": "..."} as code blocks."""
    if not strings:
        return []
    out = ["### Search strings" if notion else "## Search strings", ""] if not notion else \
          ["### Search strings"]
    for name, text in strings.items():
        if isinstance(text, dict):      # {"query": "...", "note": "..."}
            note, text = text.get("note"), text.get("query", "")
        else:
            note = None
        label = f"**{notion_text(name)}**" if notion else f"**{name}**"
        if note:
            label += f" – {notion_text(note) if notion else note}"
        out += [label, "```", str(text).strip(), "```"]
        if not notion:
            out.append("")
    return out


def render_notion(rows: list[dict], topic: str, intro: str, day: dt.date,
                  synthesis: str = "", strings: dict | None = None) -> str:
    grouped = group(rows)
    out = [f"## {notion_text(heading(topic, day))}"]
    if intro:
        out.append(notion_text(intro))
    if synthesis.strip():
        out.append("### Synthesis")
        out.append(synthesis.strip())
    out += search_strings_blocks(strings, notion=True)
    for key, items in grouped.items():
        if not items:
            continue
        out.append(f"### {notion_text(CATEGORIES[key][0])} ({len(items)})")
        out.append('<table fit-page-width="true" header-row="true">')
        out.append("<tr>\n" + "\n".join(f"<td>{c}</td>" for c in COLUMNS) + "\n</tr>")
        for row in items:
            values = cells(row, key)
            rendered = [notion_text(v) for v in values]
            rendered[4] = notion_link(values[4])
            out.append("<tr>\n" + "\n".join(f"<td>{v}</td>" for v in rendered) + "\n</tr>")
        out.append("</table>")
    return "\n".join(out) + "\n"


def render_markdown(rows: list[dict], topic: str, intro: str, day: dt.date,
                    synthesis: str = "", strings: dict | None = None) -> str:
    grouped = group(rows)
    out = [f"# {heading(topic, day)}", ""]
    if intro:
        out += [intro, ""]
    out += ["| Category | Count |", "|---|---|"]
    out += [f"| {CATEGORIES[k][0]} | {len(v)} |" for k, v in grouped.items() if v]
    out.append("")
    if synthesis.strip():
        out += ["## Synthesis", "", notion_to_gfm(synthesis.strip()), ""]
    out += search_strings_blocks(strings, notion=False)
    for key, items in grouped.items():
        if not items:
            continue
        out += [f"## {CATEGORIES[key][0]} ({len(items)})", "",
                "| " + " | ".join(COLUMNS[1:]) + " |",
                "|" + "---|" * (len(COLUMNS) - 1)]
        for row in items:
            out.append("| " + " | ".join(gfm_text(v) for v in cells(row, key)[1:]) + " |")
        out.append("")
    return "\n".join(out)


def notion_to_gfm(text: str) -> str:
    """Best-effort: drop Notion-only escapes so the synthesis reads well on GitHub."""
    text = text.replace("<empty-block/>", "")
    return re.sub(r"\\([\\*~`$\[\]<>{}|^])", r"\1", text)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("rows", help="JSON file with a list of curated rows")
    p.add_argument("--topic", required=True)
    p.add_argument("--intro", default="", help="summary paragraph under the heading")
    p.add_argument("--synthesis", help="Notion-flavoured Markdown file inserted as 'Synthesis'")
    p.add_argument("--search-strings", help="JSON {database: query | {query, note}}")
    p.add_argument("--date", help="YYYY-MM-DD (default: today)")
    p.add_argument("--notion", help="write Notion-flavoured Markdown here")
    p.add_argument("--markdown", help="write GitHub Markdown here")
    args = p.parse_args(argv)

    rows = json.loads(Path(args.rows).read_text(encoding="utf-8"))
    day = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    synthesis = Path(args.synthesis).read_text(encoding="utf-8") if args.synthesis else ""
    strings = json.loads(Path(args.search_strings).read_text(encoding="utf-8")) \
        if args.search_strings else None
    if not (args.notion or args.markdown):
        p.error("give --notion and/or --markdown")
    for target, render in ((args.notion, render_notion), (args.markdown, render_markdown)):
        if target:
            Path(target).parent.mkdir(parents=True, exist_ok=True)
            Path(target).write_text(render(rows, args.topic, args.intro, day, synthesis, strings),
                                    encoding="utf-8")
            print(f"wrote {target}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
