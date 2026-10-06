# People: key authors, co-authors, reviewers, data owners

Goal: a table of researchers and practitioners whose work matters for the research question
and who could plausibly become co-authors, discussants, reviewers, special-issue editors,
interview partners or data owners. Three location tiers: **Wien**, **Österreich**,
**Global**. Aim for a mix of (a) the central authors of the literature found by the other
agents, (b) rising scholars publishing in the last five years, (c) editors and special-issue
guest editors on the topic, and (d) practitioners or institutions that hold data.

## Where to look

- The article rows themselves: who recurs as author, who is cited by everyone (OpenAlex
  author grouping via `search_sources.py -c people -q "<topic>"` returns the most productive
  authors with affiliation; Google Scholar / OpenAlex author pages for citation context)
- Editorial boards and special-issue calls: JIBS, JWB, GSJ, JIM, MIR, IBR, SMJ, Organization
  Studies, JM, JIMk; AIB, EIBA, AOM (IM and STR divisions), SMS, EMAC programme listings
- Austrian institutions: WU Wien (Institute for International Business, International
  Marketing Management, Strategic Management), Uni Wien, JKU Linz (IB), Uni Graz, Uni Innsbruck,
  MODUL, FH Wien der WKW, wiiw (Vienna Institute for International Economic Studies), WIFO,
  OeNB research, Complexity Science Hub, Austrian Chamber of Commerce (WKO) foreign trade
- Global: research-group pages, personal websites, Google Scholar, ORCID, OpenAlex, LinkedIn
  public profiles, conference keynote lists, podcast appearances, Substack / blog authors
- Data owners: statistical offices, international organisations, alliance databases (SDC,
  Zephyr, Orbis), company registries, survey consortia

## What to record (professional information only)

| Column | Content |
|---|---|
| Title | full name as used professionally |
| Authors / Source / Year | current affiliation and role; location tag **Wien**, **Österreich** or **Global**; type: academic / practitioner / editor / data owner |
| Outlet / Rank | main outlets they publish in (e.g. JIBS, SMJ) |
| Link | one main public professional profile (institution page, Google Scholar, ORCID, personal site, LinkedIn public profile) |
| Key content | what they have published or built on the topic: 2 to 4 key works with years, methods they use, datasets they own |
| Relevance for the research question | co-author, discussant, reviewer, special-issue editor, data access or interview fit; format and language |
| Status | link verified / confirmed in search results / link unverified |

Only use information from public professional profiles and publications. Do not record
private contact data (personal e-mail, phone, home address), personal characteristics, or
anything from non-professional social media. Where an institutional e-mail is on an
official page, "contact via institute page" is enough.

## Quality

A good row says what the person has actually done on the question (a paper, a dataset, a
special issue, a conference track) and why that matters for the planned study. Avoid
generic "IB professor" rows without topic link. 10 to 25 well-chosen people beat 60 names.
