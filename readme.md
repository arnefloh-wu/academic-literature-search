# academic-literature-search

Automated academic literature search, built as a Claude Code skill
(`.claude/skills/academic-literature-search/`). One research topic or research question in,
four outputs out:

| Output | Where |
|---|---|
| Synthesis, reproducible search strings (EBSCO, Web of Science, Scopus, Primo, Scholar) and source tables (9 categories, journal grades, links, key content, relevance, status) | Notion: subpage of [Academic Literature Search](https://app.notion.com/p/3f164d53209a81b38950cb5f64506bad) |
| Files that may be stored (open-access PDFs, data, replication code), README, rows, bibliography | Dropbox: `Academic Literature Search/<topic>/` |
| References with full metadata | Zotero: private group "Academic Literature Search", one collection per topic; plus `bibliography.{json,bib,ris,md}` (CSL-JSON, BibTeX, RIS, APA 7) |
| README, `rows.json`, `notion.md`, `concepts.json`, `search_strings.json`, `synthesis.md`, bibliography, files | this repo: `topics/<topic>/` |

Categories: Books & Book Chapters, Journal Articles (flagged with AJG 2024 / VHB-JOURQUAL 3 /
FT50), Working Papers & Unpublished Materials, Reports, Data, Websites, Blogs, Events & Calls,
People (key authors, co-authors, reviewers, data owners in Wien / Österreich / global).

## Usage

In Claude Code (desktop or CLI) inside this repository, paste the topic or question:

```
/academic-literature-search Differentiated International Integration in International Alliances
```

The skill runs autonomously: parallel research agents search open APIs (OpenAlex, Crossref,
Semantic Scholar, CORE, DOAJ, arXiv, OSF, World Bank, Google Books, Zenodo, Dataverse,
GitHub), WU-licensed APIs when keys are present (Primo/CatalogPLUS, Scopus, Web of Science,
Springer, EBSCO), the Consensus paper search and the web, in English and German. Links are
checked, storable files downloaded, a synthesis written, and the results stored in Notion,
Zotero, Dropbox and `topics/<topic>/`. Re-running a topic updates the existing page:
carried-over rows are marked `existing`, additions `new`.

### Setup (once)

1. Copy `.claude/skills/academic-literature-search/.env.example` to `.env` in the same folder
   and fill in the keys you have. `python .claude/skills/academic-literature-search/scripts/search_sources.py --list`
   shows which connectors are active. Everything works without keys (web-search fallback);
   the Zotero key (for the automatic library sync) and a WU Primo key add the most.
2. Connect the Notion and Dropbox connectors in Claude Code (page creation and text uploads).
   Binary uploads to Dropbox need a Dropbox app token in `.env`.
3. Zotero: create a private group "Academic Literature Search" and an API key with
   read/write access to it, then set `ZOTERO_KEY` and `ZOTERO_GROUP` (steps in the
   skill's SKILL.md, section "Zotero group setup"). In cloud sessions add both as environment
   variables and allow `api.zotero.org` under Network access. Test with
   `python .claude/skills/academic-literature-search/scripts/zotero_sync.py --check`.
4. Python 3.10+; the scripts use only the standard library.

### Scripts

| Script | Purpose |
|---|---|
| `search_sources.py` | query up to 22 APIs, normalised JSON, de-duplicated |
| `search_strings.py` | concept file to EBSCO / WoS / Scopus / Primo / Scholar Boolean strings |
| `verify_links.py` | HTTP-check each link, set status label (runs on GitHub Actions via `.github/workflows/link-check.yml` whenever a `rows.json` changes) |
| `fetch_assets.py` | download open files for Dropbox/GitHub |
| `merge_rows.py` | merge previous and new rows (update runs) |
| `parse_notion_rows.py` | existing Notion page to rows JSON |
| `build_output.py` | rows JSON to Notion markdown + GitHub README |
| `build_bibliography.py` | rows JSON to CSL-JSON, BibTeX, RIS, APA 7 |
| `zotero_sync.py` | topic collections and items in the Zotero group; `--group` picks another group per search; `--update` corrects items already synced; `--check` tests key and access |
| `dropbox_upload.py` | upload a folder tree to Dropbox |

## Topics

| Topic | Rows | Notion |
|---|---|---|
| [Differentiated International Integration in International Alliances](topics/Differentiated%20International%20Integration%20in%20International%20Alliances/) | 208 | [Differentiated International Integration in International Alliances](https://app.notion.com/p/3f164d53209a8152b182f9b8c14c99c0) |
