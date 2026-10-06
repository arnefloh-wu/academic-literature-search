---
name: academic-literature-search
description: >-
  Automated academic literature search for a research topic or research question. Use
  whenever Arne pastes a research topic or question and wants the literature, sources,
  references, a reading list, a literature map, Literatur or Quellen for it, a new Notion
  topic page under "Academic Literature Search", a Zotero collection or bibliography for a
  topic, or asks to "search the literature on <topic>" / "run the academic search". Fans out
  parallel agents over open and WU-licensed sources plus web search, in English and German,
  across nine categories (books and chapters, journal articles with AJG/VHB/FT50 grades,
  working papers and unpublished materials, reports, data, websites, blogs, events, people),
  writes a synthesis and reproducible EBSCO / Web of Science / Scopus search strings, and
  stores the result as a Notion subpage, a Dropbox subfolder, a Zotero subcollection with
  bibliography files, and a GitHub topic folder.
---

# Academic Literature Search

Build a complete, link-checked literature guide for one research topic or research question
and store it in four places: a Notion subpage, a Dropbox subfolder, a Zotero subcollection
(plus bibliography files) and a folder in the GitHub repo
`arnefloh-wu/academic-literature-search`. The reference result is the Notion page
"Differentiated International Integration in International Alliances": aim for that depth
and tone. Everything is in English.

## Step 0: Get the topic

The user pastes a short text: a research topic or a research question. Take it **as typed**
for the Notion page title, the Dropbox subfolder, the Zotero subcollection and the GitHub
folder `topics/<topic>/`. Folder and collection names cannot contain `/`: replace each `/`
with ` & `; the Notion title keeps the original. If the text is a full question, use its
noun phrase as the title (e.g. "How do partners differentiate integration in international
alliances?" becomes "Differentiated Integration in International Alliances") and quote the
full question in the intro.

If the user adds context (theory lens, method, target journal, time window, region), keep
it for the "Relevance for the research question" column and the synthesis. Ask nothing
else; run fully autonomously to the end and report once with the links.

## Step 1: Set up

1. `python scripts/search_sources.py --list` shows which API connectors have keys. Read
   `references/sources.md` for coverage, the WU-licensed options and the key situation.
   Missing keys are not blockers: agents fall back to web search, WebFetch and the
   Consensus MCP and mark such rows "confirmed in search results". In cloud sessions the
   scholarly API hosts are usually blocked by the network policy (see the note in
   `references/sources.md`); then skip the scripts' network connectors entirely and tell the
   agents to use Consensus, web search and WebFetch.
2. Check for a previous run: search Notion for a subpage with the topic title under
   "Academic Literature Search" (page `3f164d53209a81b38950cb5f64506bad`) and look for
   `topics/<topic>/rows.json` in the repo. If either exists, this is an **update run**:
   fetch the old page, `python scripts/parse_notion_rows.py old_page.md -o old_rows.json`
   (or take the old `rows.json` directly), and merge later (Step 4). Existing rows keep the
   prefix "existing", new ones get "new".
3. Create `topics/<topic>/` in the repo (on `main`, pulled fresh) and the Dropbox subfolder
   `/Academic Literature Search/<topic>` (Dropbox MCP `create_folder`).
4. Interpret the question in three or four sentences for the agents: what the construct
   means, which literatures it touches (home discipline and adjacent ones), what an
   empirical study would need. Write the concept file `topics/<topic>/concepts.json`
   (see `references/search-strings.md`) and render the search strings:
   `python scripts/search_strings.py topics/<topic>/concepts.json -o topics/<topic>/search_strings.json`.
   The agents receive the strings as query ideas; the Notion page shows them for EBSCO,
   Web of Science, Scopus, Primo and Google Scholar.

## Step 2: Search in parallel

Spawn research agents (general-purpose) with `run_in_background: true`, one per block, and
give each one: the topic as pasted, your interpretation, the languages (search in **English
and German**), the row schema from `references/output-format.md`, the output file path
`topics/<topic>/agent_<X>.json`, and the instruction to write a JSON list only. Blocks
(combine for a narrow topic, split further for a broad one):

| Agent | Categories | Primary tools |
|---|---|---|
| A | journal articles, core literature | Consensus MCP (`mcp__Consensus__search`), `search_sources.py -c articles` when APIs are reachable, web search for journal pages, WebFetch on DOI landing pages for volume/issue/pages/abstract; `references/journal-ranks.md` for the rank field |
| E | journal articles, adjacent literatures and methods | same tools; conceptual origins in other disciplines, meta-analyses, review articles, methods papers, marketing or economics angles |
| B | books and chapters, reports, working papers and unpublished | `search_sources.py -c books,reports,unpublished`, web search on publisher sites, Google Books, SSRN, NBER, RePEc, EconStor, AIB/AOM/EIBA programmes, ProQuest dissertation records, UNCTAD/OECD/World Bank/EU reports |
| C | data, websites, blogs, events | `search_sources.py -c data`, web search for databases (SDC, Orbis, WRDS, World Bank, UNCTAD, OECD, Eurostat), replication packages (OSF, Dataverse, Zenodo), research-group sites, blogs and podcasts, conference and special-issue calls |
| D | people | `search_sources.py -c people` (OpenAlex author grouping) when reachable, web search; read `references/people-search.md` first |

Tell every agent:

- No fixed cap on rows, but every row must earn its place: "Key content" says what the
  source finds or offers (theory, sample, method, main result, dataset variables, chapter);
  "Relevance for the research question" says why it matters for this question (theory,
  method, data, gap, context) and the access (free / open access / WU licence / paid).
  Prefer the last ten years; keep classics only when they are still the standard citation
  and say so.
- Fill the bibliographic fields (`authors` list, `year`, `outlet`, `volume`, `issue`,
  `pages`, `doi`, `item_type`, `publisher`, `isbn`, `abstract`) whenever the source shows
  them: they feed Zotero and the bibliography. Never invent a DOI or page range; leave the
  field empty if it was not seen.
- Flag journal quality in `rank` (AJG 2024, VHB-JOURQUAL 3, FT50) using
  `references/journal-ranks.md`, verifying unlisted journals by search. Weight IB and
  marketing journals, but do not exclude other fields.
- Status label per row (see `references/output-format.md`): "link verified" only if the
  agent actually fetched the page; otherwise "confirmed in search results" or
  "link unverified".
- For `search_sources.py`, write results with `-o` and read the JSON; `meta.errors` names
  connectors that were blocked. A blocked connector means fall back to web search for that
  category, not skip it.
- Write the JSON list to the file (no prose) so the rows can be merged mechanically; report
  counts and caveats in the final message.

While the agents run, write the intro paragraph for the page (topic as pasted, date,
number of agents, blocks covered, caveats) and draft the synthesis skeleton.

## Step 3: Collect, verify, download

1. Concatenate the agents' JSON into `topics/<topic>/rows_raw.json`. Drop exact duplicates
   (same DOI or same normalised title); when two agents found the same item keep the richer
   note and the more complete bibliographic fields.
2. `python scripts/verify_links.py topics/<topic>/rows_raw.json -o topics/<topic>/rows.json`
   fetches every link and upgrades or downgrades the status label. Publisher sites that
   answer 403 keep the agent's label; the HTTP result lands in `link_check`. In cloud
   sessions most hosts fail with network errors and keep their labels: say so in the report.
3. `python scripts/fetch_assets.py topics/<topic>/rows.json -d topics/<topic>/files/`
   downloads what may legally be stored: open-access PDFs, datasets, replication code and
   permissively licensed material. It skips paywalled publisher URLs. Store nothing that
   would violate a licence; paywalled items are listed with a link only.

## Step 4: Synthesis and outputs

Write `topics/<topic>/synthesis.md` in Notion-flavoured Markdown (bold labels and bullet
lists, no `#` headings; escape `* ~ [ ] < > | ^` in prose): research streams and
theoretical lenses found, methods and data used, where the question sits, gaps and
opportunities, and five must-reads with one line each. Base every sentence on the rows.

```
python scripts/merge_rows.py old_rows.json topics/<topic>/rows.json -o topics/<topic>/rows.json   # update runs only
python scripts/build_bibliography.py topics/<topic>/rows.json -o topics/<topic>/bibliography --title "<topic>"
python scripts/build_output.py topics/<topic>/rows.json --topic "<topic>" --intro "<intro>" \
    --synthesis topics/<topic>/synthesis.md --search-strings topics/<topic>/search_strings.json \
    --notion topics/<topic>/notion.md --markdown topics/<topic>/README.md
```

The builder renders one H3 table per category in the fixed column order *Category | Title |
Authors / Source / Year | Outlet / Rank | Link | Key content | Relevance for the research
question | Status*, after the Synthesis and Search strings sections. The README is the
GitHub-flavoured copy with a category count table on top. The bibliography comes as
CSL-JSON, BibTeX, RIS and an APA 7 reference list (`bibliography.{json,bib,ris,md}`).

## Step 5: Store

**Notion.** Create (or, in update runs, `replace_content` on) the subpage under
"Academic Literature Search" with the title `<topic>` and the content of `notion.md`:
Notion MCP `create-pages` with `parent: {type: page_id, page_id:
3f164d53209a81b38950cb5f64506bad}`. Pages above ~100 rows may need the content split:
create the page with the intro, synthesis, search strings and the first tables, then
`insert_content` at the end for the rest. Read `notion://docs/enhanced-markdown-spec` first
if it is not already in context.

**Zotero.** `python scripts/zotero_sync.py topics/<topic>/rows.json --topic "<topic>"`
creates the collection "Academic Literature Search" (once), the subcollection `<topic>` and
one item per reference row, skipping items already there; it writes `zotero_key` back into
the rows. Needs `ZOTERO_API_KEY` and `ZOTERO_USER_ID` in `.env` and a reachable
`api.zotero.org`. If either is missing, say so in the report and point to
`bibliography.ris` / `bibliography.json` for a manual import (File > Import in Zotero).

**Dropbox.** Parent folder: `/Academic Literature Search` (shared link
`https://www.dropbox.com/scl/fo/vjgu07emo2cqvp3ecmvmd/AEicU50mQiPJLEkcTnw8DPQ?rlkey=ox7u0ptddzhyuv2zz9ort2fu9`).
Upload into `/Academic Literature Search/<topic>`: `README.md`, `rows.json`,
`search_strings.json`, `synthesis.md`, `bibliography.{json,bib,ris,md}` and everything in
`files/`. Two routes:

- The Dropbox MCP connector (`create_folder`, `create_file`) handles folders and text files
  (Markdown, JSON, BibTeX, RIS, CSV).
- Binary files (PDF, ZIP, XLSX) need `python scripts/dropbox_upload.py "topics/<topic>/" "/Academic Literature Search/<topic>"`
  with a Dropbox app token in `.env`. If no token is set, say so and list the files that
  stayed local.

**GitHub.** Commit `topics/<topic>/` (README.md, rows.json, notion.md, concepts.json,
search_strings.json, synthesis.md, bibliography files, files/ except anything over 50 MB)
to `main` and push. Commit message: `Add literature search for <topic>` or
`Update literature search for <topic> (<n> new rows)`. Add the topic to the table in the
repo `readme.md`.

## Step 6: Report

One short message: Notion page link, Dropbox folder path, Zotero collection (or the import
file if the sync could not run), GitHub folder link, row counts per category, how many links
verified, which connectors were skipped for lack of keys or blocked by the network, and what
the researcher should check by hand (unverified grades, paywalled items, licence questions).

## Quality bar (why it matters)

The page replaces days of database work before a paper is designed. A row that only repeats
a title wastes time; a row that names the theory, the sample, the method and the finding
saves it. An unverified link labelled "verified" or an invented DOI costs trust in the whole
table and in the Zotero library, so label honestly and leave fields empty rather than guess.
Prefer fewer, better-annotated rows over padding, but do not stop early when a block is rich.

## Files

- `scripts/search_sources.py`: 22 API connectors, normalised JSON (`--list` shows key status)
- `scripts/search_strings.py`: concept file to EBSCO / WoS / Scopus / Primo / Scholar strings
- `scripts/verify_links.py`: HTTP check and status relabelling
- `scripts/fetch_assets.py`: downloads storable open files into `files/`
- `scripts/merge_rows.py`: merge previous and new rows for update runs
- `scripts/parse_notion_rows.py`: Notion page markdown to rows JSON
- `scripts/build_output.py`: rows JSON to Notion markdown and GitHub README
- `scripts/build_bibliography.py`: rows JSON to CSL-JSON, BibTeX, RIS and APA 7
- `scripts/zotero_sync.py`: collection and items in Zotero via the Web API
- `scripts/dropbox_upload.py`: upload a folder tree to Dropbox via API token
- `references/sources.md`: source catalogue, WU licences, data sources, how to get each key
- `references/output-format.md`: row schema, categories, status labels, table layout
- `references/search-strings.md`: concept file and database syntax
- `references/journal-ranks.md`: AJG / VHB / FT50 grades for IB, management, marketing journals
- `references/people-search.md`: how to find and document key authors and co-authors
- `.env.example`: all credentials the connectors can use
