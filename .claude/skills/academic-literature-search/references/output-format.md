# Output format

## Row schema (JSON)

Every research agent returns a JSON list of rows with these keys. Strings are plain text
(no Markdown); the builder escapes and formats them. Bibliographic fields feed the Zotero
sync and the bibliography files, so fill them whenever the source shows them.

```json
{
  "category": "articles",
  "title": "Trust, Control, and Risk in Strategic Alliances: An Integrated Framework",
  "authors": ["Das, T. K.", "Teng, Bing-Sheng"],
  "year": 2001,
  "outlet": "Organization Studies",
  "rank": "AJG 4; VHB B",
  "volume": "22", "issue": "2", "pages": "251-283",
  "doi": "10.1177/0170840601222004",
  "link": "https://doi.org/10.1177/0170840601222004",
  "item_type": "journalArticle",
  "author_source": "Das and Teng, Organization Studies 22(2), 251-283, 2001, article",
  "note": "Conceptual framework linking goodwill/competence trust, behavioural/output/social control and relational/performance risk in alliances; the control dimension is the usual starting point for 'how much integration'.",
  "relevance": "Theory: control-trust lens for differentiated integration; cited 2,800+ times; paywalled, WU licence.",
  "abstract": "",
  "status": "new; link verified",
  "access": "wu_licence",
  "files": []
}
```

| Key | Required | Content |
|---|---|---|
| `category` | yes | one of the keys below |
| `title` | yes | title, or dataset / site / person name |
| `authors` | for references | list of names, "Family, Given" preferred; organisations as one string |
| `year` | for references | publication year (integer); `"n.d."` only if truly undated |
| `outlet` | for references | journal, book publisher, series, repository (SSRN, NBER), website or blog name; for people: affiliation |
| `rank` | articles | journal quality: AJG 2024 grade, VHB-JOURQUAL 3, FT50, SJR quartile; see `references/journal-ranks.md`; empty for non-journal items |
| `volume`, `issue`, `pages` | articles, chapters | as printed |
| `doi` | if exists | bare DOI (`10.xxxx/...`) |
| `isbn`, `publisher`, `editors`, `book_title`, `report_number` | books, chapters, reports | as applicable |
| `item_type` | recommended | Zotero type: journalArticle, book, bookSection, report, preprint, conferencePaper, thesis, dataset, webpage, blogPost, manuscript (inferred from category when missing) |
| `link` | yes | one canonical URL (DOI link for publications; profile URL for people) |
| `author_source` | yes | one-line human form: authors, venue, year, type (used in the Notion table) |
| `note` | yes | **key content**: what the source says or offers (theory, sample, method, main finding, dataset variables, chapter) |
| `relevance` | yes | **relevance for the research question**: theory / method / data / gap / context; plus access: free, open access, WU licence, paid |
| `abstract` | optional | abstract if available (goes to Zotero) |
| `status` | yes | see labels below |
| `access` | no | `free`, `open_access`, `paid`, `wu_licence`, `login` |
| `files` | no | filenames saved by `fetch_assets.py` (filled by the script) |
| `link_check` | no | HTTP result written by `verify_links.py` |
| `zotero_key`, `cite_key` | no | written by `zotero_sync.py` and `build_bibliography.py` |

## Categories

| key | Notion heading | What belongs here |
|---|---|---|
| `books` | Books & Book Chapters | monographs, edited volumes, handbook chapters, textbooks |
| `articles` | Journal Articles | peer-reviewed journal articles, review articles, meta-analyses, research notes |
| `unpublished` | Working Papers & Unpublished Materials | SSRN/NBER/CEPR/RePEc working papers, preprints (arXiv, OSF, EconStor), conference papers (AIB, AOM, EMAC, EIBA, SMS), dissertations, registered reports, manuscripts under review |
| `reports` | Reports | reports by international organisations (UNCTAD, OECD, World Bank, WTO, EU), consultancies, industry bodies, central banks, statistical offices |
| `data` | Data | datasets and databases usable for empirical work: variables, coverage, access and licence (Orbis, SDC Platinum, Zephyr, Compustat/WRDS, World Bank, UNCTAD, OECD, Eurostat, replication packages, surveys) |
| `websites` | Websites | reference sites, documentation, research-group pages, portals, literature hubs |
| `blogs` | Blogs | research blogs, Substack/Medium, podcasts, LinkedIn newsletters with substance on the topic |
| `events` | Events & Calls | optional: conferences, special-issue calls, workshops, paper development workshops relevant to the question |
| `people` | People | key authors, research groups, potential co-authors, reviewers and special-issue editors (see people-search.md) |

## Status labels

The label has two parts separated by `; `: run marker and verification.

- Run marker: `new` (added in this run) or `existing` (carried over from a previous run by
  `merge_rows.py`); `manual` for rows the researcher typed into Notion.
- Verification: `link verified` (the page was fetched, by the agent or by `verify_links.py`),
  `confirmed in search results` (only confirmed through search-result snippets or an API
  record), `link unverified` (constructed or remembered URL, check before use).

Agents hand over honest labels; `verify_links.py` upgrades to "link verified" when a link
answers 2xx/3xx and downgrades a "verified" claim that fails with 404/410.

## Notion page layout

```
## Sources on <Topic> (agent search, <D Month YYYY>)
<intro paragraph: research question as pasted, agents, blocks covered, row count, caveats, status legend, GitHub path>
### Synthesis
<themes, theoretical lenses, methods and data used, gaps, five must-reads, as Notion markdown>
### Search strings
<EBSCO, Web of Science, Scopus, Primo, Google Scholar, OpenAlex as code blocks>
### Books & Book Chapters (n)
<table fit-page-width="true" header-row="true">  Category | Title | Authors / Source / Year | Outlet / Rank | Link | Key content | Relevance for the research question | Status
### Journal Articles (n)
...
### People (n)
```

Sections appear in the category order above; empty categories are omitted. For People the
columns read: Category = Person; Title = name; Authors / Source / Year = affiliation, role,
location tag (Wien / Österreich / Global), type (academic / practitioner); Outlet / Rank =
main outlets they publish in; Link = professional profile; Key content = what they have
written or built on the topic; Relevance = co-author, reviewer, discussant, data-owner or
guest-speaker fit; Status = as above.

## GitHub README layout

Same sections rendered as GitHub tables (without the Category column), preceded by a
category count table. Next to it: `rows.json` (machine-readable source), `notion.md` (the
exact text pushed to Notion), `search_strings.json`, `synthesis.md`, `concepts.json` and
`bibliography.{json,bib,ris,md}`.
