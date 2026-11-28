# Amar Circular: SEO and analytics guide

Amar Circular (amarcircular.com) publishes plain summaries of Bangladesh Bank circulars for bank compliance
teams. This guide covers how the site gets found on Google and Bing, how visits are measured, and what to do each
week. Last updated 28 Nov 2026. Keyword research is in [KEYWORDS.md](KEYWORDS.md).

SEO (search engine optimisation) is the work that helps a site rank higher in Google and Bing results.

## 1. Accounts and tools

| Tool | What it is for | Account | How it was set up |
|---|---|---|---|
| Google Search Console | Google's own report on how the site appears in Google: searches, clicks, position, indexing problems | Google account hozaifah626 | Domain property `amarcircular.com`, verified with a TXT record in Cloudflare DNS. Sitemap submitted 26 Nov. |
| Bing Webmaster Tools | The same for Bing (and the search engines that use Bing's index) | Microsoft login 20hozaifa02 | Verified with a CNAME record in Cloudflare DNS. Sitemap submitted 26 Nov. |
| IndexNow | Tells Bing about new pages within the hour instead of waiting for a crawl | none (a key file) | Runs inside the backend (section 3.6). |
| OpenSEO (app.openseo.so) | Keyword volumes, competitor checks, and Search Console data in one place | 20hozaifa02 (free trial) | Project "amarcircular.com", market Bangladesh. Search Console linked 28 Nov through hozaifah626 (section 5). |
| PostHog | Visitor analytics: page views, time on page, clicks, heatmaps, session replays | Google sign-in, project "Amar Circular" (id 767935, US region) | Section 4. |
| Cloudflare | DNS for the domain; all verification records live here | 20hozaifa02 | Proxy on, SSL Full (strict). |

Google does not use IndexNow. It finds new pages through the sitemap and links, so Search Console is the place
to watch for Google.

## 2. How search traffic works for this site

People search for Bangladesh Bank circulars by department and number ("brpd circular 15 2024",
"bfiu circular 26") or by subject ("loan classification circular"). Most of these phrases have low competition.
The main rivals are bb.org.bd (the PDFs, with no summaries), news sites and regalert.today.

Amar Circular has one page per circular, titled with the exact reference, plus list pages by department, year and
subject. So the work comes down to four things:

1. Get pages indexed (sitemap, IndexNow, Search Console).
2. Make sure the most-searched circulars are summarised and marked **Ready**. Only Ready circulars can be indexed.
3. Write a few longer guides on the subjects people search most (planned, section 7).
4. Earn links and mentions from LinkedIn, Facebook banker groups and other sites (planned, section 7).

## 3. What is built into the site

### 3.1 Which pages are indexable

- A circular page can be indexed only when its circular is **Ready**, meaning the analysis passed the automatic
  checks (stored status `PUBLISHED_MACHINE_VERIFIED`, see `INDEXABLE` in `backend/app/modules/library/public.py`).
- A circular still marked **Analysing** opens at its address but carries `noindex`. That tag asks search engines
  to leave the page out of their results, which keeps half-finished pages out of Google. The owner chose this rule
  on 26 Nov (DECISIONS.md 16).
- A list page (department, year or subject) is indexable only when it holds at least 3 Ready circulars
  (`HUB_MIN_INDEXABLE`).
- To get a much-searched circular indexed, get it to Ready (section 6.2).

### 3.2 Page addresses and titles

- Circular pages: `/circular/<dept>/<number>-<year>-<title words>`, for example
  `/circular/brpd/15-2024-master-circular-loan-classification-and-provisioning`.
- Page title: the exact reference first, then the subject: "BRPD Circular No. 15/2024: Master Circular: Loan
  Classification and Provisioning. | Amar Circular". This matches how people type their searches.
- Each page sets a canonical address, a description, and Open Graph and Twitter card tags
  (`frontend/app/circular/[dept]/[slug]/page.tsx`). The canonical address tells search engines which URL is the
  main copy of the page. Open Graph and Twitter card tags control the preview shown when a link is shared.
- List pages: `/circulars` (all, newest first), `/circulars/<dept>` (for example `/circulars/brpd`),
  `/circulars/<year>`, `/circulars/topic/<subject>`.

### 3.3 Structured data

Structured data is a block of machine-readable facts about a page that search engines read alongside the text.
The site writes it as schema.org JSON-LD. Each circular page describes itself as an `Article` written and published
by the organisation "Amar Circular", about the `GovernmentOrganization` "Bangladesh Bank", with a breadcrumb trail
(Home > Circulars > department > circular). List pages carry a breadcrumb trail and an `ItemList`
of their circulars (`frontend/components/seo/CircularHub.tsx`).

### 3.4 Sitemap and robots

- `https://amarcircular.com/sitemap.xml` (`frontend/app/sitemap.ts`) lists the home page, `/circulars`, every
  indexable list page and every Ready circular. It is built on request and the circular list is cached for an hour.
- `https://amarcircular.com/robots.txt` (`frontend/app/robots.ts`) allows the public pages and blocks admin,
  workspace, alerts, API and account pages.

### 3.5 llms.txt

`https://amarcircular.com/llms.txt` (`frontend/app/llms.txt/route.ts`) is a plain-text map of the site for chat
assistants and answer engines such as ChatGPT and Perplexity (format from llmstxt.org): list pages, subjects and the 40 newest summarised
circulars. It refreshes every hour.

### 3.6 IndexNow

- Code: `backend/app/modules/library/indexnow.py`. It runs only on the live server. It starts 3 minutes after the
  backend starts, then runs every hour.
- Each round it lists every public page, sends the ones not sent before to `api.indexnow.org`, and records them in
  `/opt/regwatch/app/data/indexnow_sent.txt`. The home page and `/circulars` are sent again whenever anything new
  goes out.
- The key file is public by design: `https://amarcircular.com/60b49caa6f7be62ceb2165ea3dc93699.txt`
  (`frontend/public/`).
- Check it on the server: `sudo wc -l /opt/regwatch/app/data/indexnow_sent.txt` should grow as circulars become
  Ready. The file is written only when IndexNow accepts the batch. On 28 Nov it held 505 pages.

## 4. Visitor analytics (PostHog)

- Code: `frontend/services/analytics.ts` and `frontend/components/Analytics.tsx`.
- It runs only on amarcircular.com (and www), so local testing never adds fake visits. To test elsewhere, set
  `NEXT_PUBLIC_POSTHOG_ANY_HOST=1`. The project key can be overridden with `NEXT_PUBLIC_POSTHOG_KEY`.
- Traffic goes through `/ingest` on our own domain (rewrites in `frontend/next.config.js`), so ad blockers do not
  drop it.
- Recorded: page views (with the page title), time on page, clicks (autocapture), dead clicks, heatmaps and session
  replays. All typed text is masked, so passwords and emails never leave the browser.
- Signed-in readers are identified by account id, with email, name, phone and an admin flag. Company and
  designation are added when a reader finishes sign-up step 3. Signing out starts a fresh anonymous visitor.
- Named events: `signed_up` and `signup_details_completed` (with company, designation and institution type).
  Add more with `track("event_name", {...})`.
- Project settings done: session replay on, heatmaps on, time zone Asia/Dhaka.
- Still to do: an internal-users filter on `is_admin = true`, so our own visits don't count.

Where to look: us.posthog.com, project "Amar Circular". Web analytics shows traffic and sources; Replay shows
recorded visits; Heatmaps shows where people click on a page.

## 5. Search Console through OpenSEO

Search Console data can be read in the Search Console website, or through OpenSEO. OpenSEO's Search Console
reports use no credits.

Setup (done 28 Nov):

1. OpenSEO project "amarcircular.com" (market Bangladesh) on the 20hozaifa02 account.
2. GSC Insights > account menu > Add Google account > hozaifah626 (read-only access to Search Console).
3. Property `sc-domain:amarcircular.com` chosen for the project.

If the link ever breaks (Google access removed, password changed), repeat step 2 and pick the property again.

## 6. Routine work

### 6.1 Weekly check (about 20 minutes)

1. In Search Console > Pages, see how many pages are indexed and why others are not. "Crawled, currently not
   indexed" on Ready pages is normal in the first weeks.
2. In Search Console > Performance, set the last 7 days and note clicks, impressions and average position. An
   impression is one appearance of our page in someone's search results. Queries at position 5 to 20 that get
   impressions are close to page one, so those pages give the most return for improvement.
3. Compare the queries with KEYWORDS.md. A searched circular that is missing or still Analysing goes on the task
   list (section 6.2).
4. In Bing Webmaster Tools, check indexed pages and crawl errors.
5. In PostHog, check visitors, top pages and sign-ups (`signed_up`), and watch a few replays of visitors who came
   from search.
6. Write the numbers into the TickTick task before ticking it off.

### 6.2 Getting a searched circular to Ready

- If the circular is missing from the library, find it on bb.org.bd and check why the checker or the archive
  import missed it. On 28 Nov BRPD Circular No. 15/2024 turned out to be in the database but hidden: a test record
  with the same number had taken the real PDF. The import now never matches a test record.
- If it is in the library but stuck on Analysing with points still "checking", its second reading has not run.
  The second reading reads the page image again and compares it with our text. Run it for that circular's current
  version on the server, early in the day, before the background job uses up the free Gemini quota:
  `cd /opt/regwatch/app && sudo -u regwatch .venv/bin/python backend/scripts/second_read.py <version_id>`
- If it is in the library with no analysis, analyse it through the Phase 1 flow (`backend/scripts/phase1_sync.py`
  and the analysis repo's RUNBOOK.md).
- Once Ready, the page joins the sitemap within the hour, and IndexNow sends it to Bing in its next round. For an
  important page, also use Search Console > URL inspection > Request indexing.

### 6.3 After a deploy that changes page structure

Open one circular page and one list page and check: the title starts with the reference,
`<meta name="robots" content="index, follow">` is present on a Ready page, the JSON-LD script is there, and the page
appears in `/sitemap.xml`.

## 7. Plan (dates are TickTick tasks in the "amarcircular seo" list)

| Date | Task |
|---|---|
| 30 Nov | Excise duty circular page (Search Console already shows this search at position 1) |
| 1 Dec | Request indexing for the top pages in Search Console |
| 2 Dec | LinkedIn page for Amar Circular and a first post |
| 3 Dec | Facebook page, shared in banker groups |
| 5 Dec | Share image for links (Open Graph image) |
| 8 Dec, then every Tuesday | Weekly SEO check (section 6.1) |
| 9 Dec | Page speed check |
| 10, 17, 24, 31 Dec | Guides: loan rescheduling rules; BFIU Circular 26 summary (AML/KYC); loan classification and provisioning rules; cash incentive and remittance incentive rates |
| 6 Jan | Keyword refresh and rank check |
| 14 Jan, 14 Feb | Monthly SEO reports |

## 8. Where things stand (Search Console, 29 Oct to 25 Nov 2026)

The site launched on 24 Nov, so this covers its first days in Google.

- First impressions were recorded on 25 Nov: 93 impressions, 4 clicks, average position 5.7.
- Top page: `/circulars/brpd` (32 impressions, 2 clicks, average position 7.3).
- Searches already reaching us: "brpd 23 2026", "brpd circular 30 2026", "acd circular 1 2026",
  "excise duty circular bangladesh bank 2026" (position 1), "brpd circular no 16 master circular on loan
  rescheduling and restructuring".
- Library on 28 Nov: about 450 circulars Ready, about 220 still Analysing.
- 28 Nov: BRPD Circular No. 15/2024 and BRPD Circular Letter No. 26/2025 (about 140 and 170 searches a month)
  became Ready and indexable.
