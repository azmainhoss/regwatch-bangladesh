# Research 1: detecting new Bangladesh Bank circulars (2026-11-10)

Checked against the live site from a home connection in Bangladesh: 14 polite requests, no bot challenge.
Raw responses are in the session scratchpad (scrape_research/raw).

## Verified on the live site
- **Best signal: a small, server-side date filter.** The circular page's search form accepts a date range:
  `POST https://www.bb.org.bd/en/index.php/mediaroom/circular`
  body `from_date=2026-11-01&to_date=2026-11-09&search_circular=Search` (yyyy-mm-dd, `to_date` inclusive).
  It needs no token or cookie. It returned 51 KB in 0.28 s with only that week's circulars, in the same table format.
  The full listing is 2.6 MB in 2.3 s, so this is about 50 times lighter.
- **Full listing:** 2.6 MB with all 4,816 rows and no gzip. Use it only for a nightly double-check and the one-time backfill.
- **Homepage ticker** (77 KB, 0.5 s): the 5 newest circulars, plus notices, MPC resolutions and draft guidelines.
- **No feed of any kind:** no RSS, sitemap, JSON API or email alerts. The only contact is webmaster@bb.org.bd.
  Official channels: Facebook BangladeshBankOfficial, X centralbankbd, YouTube, Android app bd.org.bb.cms.
- **Bangla site** is just a language toggle. The English list already carries Bangla PDF links and Bangla-only circulars.
- **Bot protection:** F5 BIG-IP (TS cookies, /TSPD/ JavaScript check).
- **PDFs:** they return ETag and Last-Modified. Recent uploads were 14:53-17:28 Bangladesh time, all on working days.
- **News sites:** sometimes post the same day, even before the PDF timestamp, but only for newsworthy circulars.
- **Outages:** BB took its website offline on 22 Oct 2026 (Dhaka Tribune).

## Recommended design
- **Main check:** the date-filter POST for the last 7 days. Key each row by its PDF URL and compare parsed rows, not raw HTML.
  A "200 but no table" response counts as a fault, not as "nothing new".
- **Schedule:**
  - every 10 min (with ±2 min jitter) Sun-Thu 09:00-19:00 BST; hourly outside those hours;
  - every 5 min for an hour after a new item appears.
  - That comes to about 3 MB a day in total.
- **Backups:**
  - homepage ticker every 30 min;
  - notice board and press release pages;
  - a nightly full-list check at about 02:00;
  - PDF ETag re-checks to catch silently replaced files;
  - news tags and RegAlert as outside cross-checks.
- **When blocked or broken:** stop, back off (30 min, rising to 6 h) and alert a person after 2 failures.
  Also alert after 3 working days with nothing new, and when the site is down.
- **Tool:** a small purpose-built script.
  - Python httpx + selectolax/lxml uses about 30-60 MB RAM; Go uses about 10-20 MB. CPU is near zero.
  - changedetection.io: OK as a quick second watcher (100-200 MB, more with a browser).
  - Crawl4AI, Firecrawl and Crawlee: overkill.
  - Playwright: only if the site starts requiring JavaScript for every visitor.
- **Hosting:** not a factor. Everything will run in Bangladesh. The "foreign IPs get blocked" idea was never proven,
  and the user confirmed blocks also happened from a Bangladeshi home connection.
- **Scope gap:** this research only compared do-it-yourself tools. Managed scraping APIs, monitoring services and
  self-hosted scraping platforms still need comparing (see DEEP_RESEARCH_PROMPT_SCRAPING.md).
- **Official access:** email webmaster@bb.org.bd asking for a feed or for one fixed IP to be allow-listed, then send a formal letter to the ICT Department.
  An RTI Act 2009 request can get information, but it can't force BB to provide a feed.

## Competitors
- **RegAlert (regalert.today):** claims 186 jurisdictions and same-day coverage. It has Bangladesh pages with BB and BFIU circular texts,
  plus an API and an MCP connector. Monitoring is free, with a reported $0.05 per full document. This is the closest direct competitor.
- **CUBE, Compliance.ai/Archer, Ascent, Regology, Corlytics:** global players with no confirmed Bangladesh coverage.
- **KPMG BD:** periodic newsletters only.
- **Local:** no Bangladeshi startup selling circular monitoring was found.

## Not verified
- the vendor coverage claims;
- the BD VPS prices;
- whether a BDIX datacenter IP passes the bot check (needs a trial month);
- whether the press-release form filters by date.

## Sources
dhakatribune.com/business/422697 · regalert.today · glama.ai/mcp/connectors/com.regmonitoring/regulatory-updates ·
dailywaadaa.com (2026/11/09 remittance story) · thereport.live (42613) · unb.com.bd/news/tag/22510 ·
community.f5.com (TSPD and JavaScript challenge) · bb.org.bd/en/index.php/services/rti · whtop.com (DianaHost, HostingBangladesh) ·
techshopbd.com (Raspberry Pi 5) · github.com/dgtlmoon/changedetection.io/wiki/Playwright-content-fetcher
