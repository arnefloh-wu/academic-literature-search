# Source catalogue

`scripts/search_sources.py --list` shows which connectors have keys. Keys go in
`.claude/skills/academic-literature-search/.env` (git-ignored) or
`~/.config/academic-search/.env`; copy `.env.example`.

## Open APIs (no key or free key)

| Connector | Covers | Key | Notes |
|---|---|---|---|
| openalex | 250M+ works: articles, books, chapters, preprints, reports, datasets | none (`OPENALEX_EMAIL` for polite pool) | best first stop; `filter=type:` per category; abstracts and citation counts |
| openalex_people | most productive authors on a query, with affiliation and ORCID | none | `-c people`; feeds the People agent |
| crossref | DOI metadata: articles, books, chapters, posted content | none (`CROSSREF_EMAIL`) | authoritative volume/issue/pages for the bibliography |
| semantic_scholar | articles and preprints with citation counts, open PDFs | optional `S2_API_KEY` | 100 req/5 min without key |
| core | open-access full texts, working papers, theses | `CORE_API_KEY` (free) | PDFs for Dropbox |
| doaj | open-access journal articles | none | |
| arxiv | preprints (econ.GN, q-fin, stat, cs) | none | rarely relevant for IB, useful for methods |
| osf | OSF Preprints: SocArXiv, PsyArXiv, MetaArXiv | none | registered reports, preregistrations |
| worldbank | World Bank Documents & Reports | none | policy research working papers |
| openlibrary, google_books | book metadata, ISBN | optional `GOOGLE_API_KEY` | |
| github | repositories: replication code, datasets | optional `GITHUB_TOKEN` | |
| zenodo, harvard_dataverse | datasets, replication packages | none | |
| kaggle | datasets | `KAGGLE_USERNAME` + `KAGGLE_KEY` | |
| data_europa, data_gov | EU / US open data | none | |

Also usable through MCP / web search in Claude Code: Consensus (`mcp__Consensus__search`,
semantic paper search with abstracts and citation counts, the main tool when APIs are
blocked), web search for publisher pages, SSRN, NBER, RePEc/IDEAS, EconStor, ProQuest
dissertation records, conference programmes, blogs and people; WebFetch for DOI landing
pages (metadata, abstract, volume/issue/pages).

Working-paper series without a connector: SSRN (search `papers.ssrn.com` via web search; the
abstract page carries the full metadata), NBER (`nber.org/papers`), CEPR Discussion Papers,
RePEc/IDEAS (`ideas.repec.org`), EconStor (`econstor.eu`), CESifo, Kiel Institute, wiiw
Working Papers (Vienna), WU Working Paper series. Conference papers: AIB and EIBA
proceedings, AOM Proceedings (`journals.aom.org/toc/amproc`), SMS, EMAC.

## WU-licensed databases

WU Bibliothek uses Ex Libris Alma with two Primo front ends ("WU-Katalog" and
"CatalogPLUS"). Database list: https://www.wu.ac.at/bibliothek/recherche/datenbanken/.
Confirmed licences: Scopus, Web of Science Core Collection, EBSCO Business Source Premier,
ABI/Inform (ProQuest), JSTOR, Emerald, wiso, Statista, Passport (Euromonitor), Orbis / Orbis
Europe, LSEG Workspace (SDC Platinum alliances and M&A), WRDS, Factiva, Panjiva.

| Connector | Database | Key / credential | How to obtain |
|---|---|---|---|
| wu_primo | WU catalogue + CatalogPLUS (books, e-books, articles, dissertations held by WU) | `PRIMO_API_KEY`, `PRIMO_VID`, optional host/scope/tab/base | Ask WU Bibliothek (systems librarian) for a Primo Search API key and the CatalogPLUS view ID. Answers "does WU have it?" directly. |
| scopus | Scopus abstracts and citations | `ELSEVIER_API_KEY`, optional `ELSEVIER_INSTTOKEN` | dev.elsevier.com with WU e-mail; works on WU network/VPN; institutional token via the library for off-campus use |
| wos | Web of Science Starter API | `CLARIVATE_WOS_API_KEY` | developer.clarivate.com, "Web of Science Starter API" (free tier for subscribing institutions) |
| springer | Springer Nature Meta API | `SPRINGER_API_KEY` | dev.springernature.com, free |
| ebsco_eds | EBSCO Discovery Service | `EDS_USER`, `EDS_PASSWORD`, `EDS_PROFILE` | only if WU has an EDS profile (uncertain). Connector untested. |

Without a usable API: EBSCO Business Source (web UI only, hence the ready-made search
string on every topic page), JSTOR, Emerald, ProQuest, Statista, Passport, Orbis, LSEG,
Factiva. Search them via the web UI with the strings in the "Search strings" section and
link the record with "WU licence".

## Data sources for empirical IB / alliance research

Alliance and deal data: LSEG SDC Platinum Joint Ventures & Alliances (WU: LSEG Workspace /
WRDS), Bureau van Dijk Zephyr and Orbis (ownership, subsidiaries), Compustat and
Compustat Global (WRDS), Crunchbase, PitchBook (check WU access), Factiva for event data.
Country-level: World Bank WDI and WGI, UNCTAD FDI and WIR data, OECD (FDI restrictiveness,
TiVA), WTO, Eurostat, Hofstede/GLOBE/Schwartz culture scores, CAGE distance, Kogut-Singh,
Berry-Guillén-Zhou distance data, Fraser Institute Economic Freedom, Heritage Index,
Polity/V-Dem, DESTA (trade agreements), EU differentiated integration datasets (EUDIFF,
Schimmelfennig and Winzen). Replication packages: OSF, Harvard Dataverse, Zenodo, journal
supplementary materials (JIBS and SMJ require data availability statements).

## Zotero

Target: a private Zotero group "Academic Literature Search", one top-level collection per
topic. Needs `ZOTERO_KEY` (read/write for the group) and `ZOTERO_GROUP` (group ID, URL or
name); the user ID is detected from the key. Setup steps: SKILL.md, section
"Zotero group setup". `zotero_sync.py --check` verifies key, permissions and reachability.
In cloud sessions `api.zotero.org` must be on the environment's allowed domains. Fallback
without key or network: import `bibliography.ris` or `bibliography.json` (CSL-JSON) via
File > Import in Zotero and drag the items into the group collection.

## Network note

In Claude Code cloud sessions most API hosts are blocked by the environment's network
policy (only package registries and GitHub pass; checked 6 October 2026). Run the skill on
a PC, or add the hosts to the environment's allowed domains: api.openalex.org,
api.crossref.org, api.semanticscholar.org, api.core.ac.uk, doaj.org, export.arxiv.org,
api.osf.io, search.worldbank.org, openlibrary.org, www.googleapis.com,
api.springernature.com, api.elsevier.com, api.clarivate.com,
api-eu.hosted.exlibrisgroup.com, api.github.com, zenodo.org, dataverse.harvard.edu,
www.kaggle.com, data.europa.eu, catalog.data.gov, api.zotero.org, content.dropboxapi.com,
api.dropboxapi.com, doi.org. Web search, WebFetch and the Consensus, Notion and Dropbox MCP
connectors work regardless, so a cloud run still produces the full page; it just verifies
fewer links by HTTP.
