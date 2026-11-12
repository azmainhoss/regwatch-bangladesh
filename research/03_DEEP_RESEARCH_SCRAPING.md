# Research 3: deep research on collecting circulars (2026-11-10)

A condensed record of the deep research report the user ran with DEEP_RESEARCH_PROMPT_SCRAPING.md.
The full original is in the user's chat.

## Verdict
**Option (c): a small purpose-built collector, one adapter per regulator, run from our own Dhaka server.**
Add two cheap independent watchers. Use a real browser session only to get normal session cookies.
Formally ask Bangladesh Bank to allow-list us. Do not use "unblocker" products.
- At about 300 circulars a year, volume and parsing are not the hard parts. The hard parts are telling a challenge page from a real
  result, and proving nothing was missed. Managed APIs solve neither.
- Expected cost: about $10-40/month infrastructure (estimate) + $8.99/month changedetection.io hosted as a canary.
- Expected detection: 5-15 minutes after a circular appears on the site.

## Key findings
- **The challenge page is F5 BIG-IP Bot Defense's standard CAPTCHA** ("What code is in the image?", "Your support ID is").
  It often comes back with **HTTP 200**, so the status code alone never proves success.
  Being blocked after about 20 downloads one time and not after 100+ another fits a score- or rate-based trigger (inferred).
- **Volume is trivial; correctness is everything.** The risks are silent misses and being blocked.
- **RegAlert (regalert.today) already collects BB circulars.** Its summaries are machine-assisted and "reviewed before publication",
  each with an "Applies to" tag and an agent interface. It's the benchmark we'll be compared against.
- **Big firms (CUBE, Corlytics, Regology) use crawlers plus large human QA teams.** None claims fully autonomous collection.
- **News is a fast second signal.** The 8 Nov 2026 BRPD-1 letter appeared the same day in BSS, Daily Star, bdnews24 and Dhaka Tribune.

## Managed scraping APIs (prices from 2026 third-party write-ups; check before buying)
| Service | Price at our volume | Note |
|---|---|---|
| Firecrawl | Free 1k credits; Hobby $19 (5k); Standard $99 (100k) | /monitor checks down to 5 min with signed webhooks and diffs. Closest managed fit. Its default proxy mode gets past bot checks, which we must not use on BB. Self-hostable (AGPL). |
| Apify | Starter about $19/mo | Hosted Crawlee code; some lock-in. |
| Zyte API | $0.13-1.27 per 1k HTTP requests | "Ban handling" built in and can't be separated. |
| Bright Data Web Unlocker | $1.50 per 1k, 5k free/mo | Explicit CAPTCHA bypass product. Highest legal risk. |
| ScrapingBee / ScraperAPI / ZenRows | $16-49/mo | Stealth proxies on credit multipliers. |
| Browserbase / Browserless / Steel / Hyperbrowser | $0.08-0.12 per browser-hour | Hosted browsers; several include CAPTCHA solving. |
| Diffbot / Jina / Exa / Tavily | n/a | Built for open-web retrieval. Weak fit. |
No vendor offers Bangladesh hosting. They all fetch from foreign IPs.

## Change-detection services
| Tool | Price | Fastest | Webhook | Structured new rows? |
|---|---|---|---|---|
| changedetection.io self-hosted | free | any | yes | text diff with CSS filter |
| changedetection.io hosted | $8.99/mo | minutes | yes | same |
| Visualping | $14-140/mo | 2 min | Business only | AI summaries |
| Distill.io | $15-80/mo | 2 min (5 s local) | from $15 | text diffs |
| Browse AI | $19-69/mo | minutes | yes | **yes, table rows** |
| Kadoa | from about $99/mo | configurable | yes | yes, self-healing, generates deterministic code |
All of them still hit the same F5 challenge. None reliably tells "challenge" from "no change".

## AI / agentic extraction (Crawl4AI, ScrapeGraphAI, Browser Use, Stagehand, Skyvern, AgentQL)
- **Not worth it for collection.** Regulator layouts rarely change, and deterministic CSS/XPath adapters plus schema checks catch breakage.
  LLM extractors can silently adapt wrongly or invent rows, and agentic browsers raise the bot score.
- **Worth it for two things:**
  - drafting a new regulator's adapter (have an LLM propose selectors, then freeze them as code);
  - post-processing (OCR, classification, summaries, obligation tagging).

## Self-hosted platforms
- **Crawl4AI server:** 4 GB RAM.
- **Firecrawl self-hosted:** 5 containers, 1-2 GB+.
- **Scrapy + Scrapyd:** light, mature retries and scheduling.
- **Crawlee:** light for HTTP, 0.5-1 GB per browser.
- **changedetection.io:** light, with a web UI.
- **Katana / spider-rs:** discovery crawlers, a weak fit.

## Law (not legal advice)
- **The Cyber Security Act 2026 (Act No. 81 of 2026)** replaced the 2025 Ordinance and keeps the same offences.
  - "Illegal access" includes access "in breach of the conditions of permission".
  - s.17, illegal access to Critical Information Infrastructure: up to 5 years and/or Tk 50 lakh.
  - s.18, ordinary systems: up to 1 year or Tk 10 lakh.
- **Bangladesh Bank was named critical information infrastructure** in the ICT Division's 2 Oct 2022 gazette (Daily Star).
  Unverified: whether it stays on the 2025-26 list of 35, and whether its public website counts.
- **No site terms of use found on bb.org.bd.** Downloading public circulars is ordinary use. Engineering around an access control is not.
- **Get a Bangladeshi lawyer's opinion** before any automated access beyond polite, cookie-respecting browsing.

## Legitimate options, ranked
1. Ask BB (ICT Dept / website management) for allow-listing or a push feed. Give a fixed IP, an honest User-Agent with an email, and our rate.
2. Polite pacing: one IP, no parallel requests, jitter, conditional GETs, and the 2.6 MB page only once a day.
3. A real browser session (Playwright persistent profile) that loads the page like a visitor. Reuse its cookies for HTTP requests.
4. On a CAPTCHA: stop, back off 30-60 min and alert a human, who may solve it in that browser session.
   No solver services, IP rotation or fingerprint spoofing.

## Reliability design
- **Classify every response:**
  - CHALLENGE: the challenge text, /TSPD/, "support ID", or no table.
  - SUSPECT: size far off, row count drops, or a known circular disappears.
  - OK: all schema checks pass.
  - PDFs need Content-Type application/pdf AND %PDF- bytes. Store SHA-256, ETag and Last-Modified.
- **Signals:**
  | Signal | How often | Role |
  |---|---|---|
  | Date-range search | 5-10 min | primary |
  | Homepage ticker | 15 min | secondary |
  | Full list | nightly | reconcile |
  | changedetection.io hosted | 15-30 min | independent canary |
  | News (BSS, Daily Star, bdnews24, Dhaka Tribune, FE, Prothom Alo) | 15-30 min | catch misses |
  | RegAlert | daily | benchmark only |
  | Facebook | manual / Graph API only | optional |
- **Backfill:** build a manifest from the full list, then download 1 file every 15-20 s between 00:00 and 06:00 Dhaka time.
  That's about 4-5 nights. Checkpoint each file. Stop for the night on the first challenge.
- **Alerts:** a dead-man's switch if there's no OK poll for 30 min in working hours or 2 h otherwise.
  Also alert on any challenge, a failed schema check, an unknown ID, a news item with no matching row after 2 h,
  or a bad PDF. Send by SMS/Telegram and email, with a "solve in browser" runbook.

## Option comparison
| | (a) Managed | (b) Self-hosted platform | (c) Purpose-built (picked) |
|---|---|---|---|
| Cost/mo | $19-99 | $20-60 + time | $10-40 + $8.99 |
| Speed | 5-15 min if it passes F5 | 5-10 min | 5-10 min; news backstop |
| Reliability | depends on foreign IPs + unblocking | good, more moving parts | highest controllable |
| Maintenance | low code, opaque failures | highest | low-moderate, about 100-300 lines per regulator |
| Lock-in | high | low | none |

## Plan from the report
1. **Week 1:** a written allow-list / feed request to BB (later NBR, BSEC, IDRA, FRC).
2. **Collector:** Python (Scrapy or httpx + Playwright) on a Dhaka VPS, fixed IP, honest User-Agent. Playwright refreshes F5 cookies only when needed.
   On a CAPTCHA, page a human. Postgres + object storage.
3. **Polling:** the date search every 5-10 min Sun-Thu 09:00-20:00, every 30 min otherwise. Nightly reconcile. Conditional GETs for PDFs.
4. **Independent watchers:** changedetection.io hosted plus news. Optionally Firecrawl Hobby /monitor without stealth proxies as a third observer.
5. **Adapter interface:** list_new_items / fetch_document / health_check. LLMs only draft selectors and handle post-processing.
6. **Backfill:** 4-5 nights, or 1 night once allow-listed.
