# Search strings for licensed databases

Every topic page carries reproducible Boolean strings so the search can be repeated (and
cited in a methods section) in EBSCO Business Source, Web of Science, Scopus and WU
CatalogPLUS. `scripts/search_strings.py` renders them from a concept file the agent writes
after reading the research question.

## Writing the concept file

1. Break the question into 2 to 4 **concepts** (population / phenomenon / context / outcome).
   Example "Differentiated International Integration in International Alliances":
   concept 1 = alliance form (international alliance, strategic alliance, international joint
   venture, cross-border partnership, alliance portfolio, multi-partner alliance);
   concept 2 = integration (integration, coordination, control, autonomy, interdependence,
   governance, "differentiated integration", "partial integration", "variable geometry").
2. For every concept list **synonyms, spelling variants and German terms** that occur in
   abstracts: `alliance*` covers alliance/alliances; `"joint venture*"` keeps the phrase.
   Add German only where the database indexes German-language journals (EBSCO: some; WoS,
   Scopus: few). Note German terms in the Notion intro instead if they add nothing.
3. Add **exclusions** only for homonyms that flood results (e.g. `nursing`, `school*`,
   `military alliance*` if not wanted).
4. Set a **year window** if the question is about recent developments; otherwise omit it
   and let the agents flag classics.

## Syntax reminders

| Database | Field codes | Truncation / phrase | Proximity | Years |
|---|---|---|---|---|
| EBSCO Business Source | TI, AB, SU, KW (one field per block) | `*`, `"..."` | `N5` (near, any order), `W5` (within, in order) | limiter "Published Date", or `DT 2015-2026` |
| Web of Science | TS (topic = title, abstract, author keywords, Keywords Plus), TI, AU, SO | `*`, `"..."` | `NEAR/5` | `PY=(2015-2026)` |
| Scopus | TITLE-ABS-KEY, TITLE, AUTHKEY, SRCTITLE | `*`, `"..."` (loose), `{...}` (exact) | `W/5`, `PRE/5` | `PUBYEAR > 2014` |
| WU CatalogPLUS (Primo) | any, title, subject, creator | `*`, `"..."` | none | facet "Creation date" |
| Google Scholar | intitle:, author: | `"..."` only, no truncation | none | custom range |

Record the string you actually ran and the hit count in the Notion intro when the run
happens in the web UI (the agents cannot see licensed hit counts).
