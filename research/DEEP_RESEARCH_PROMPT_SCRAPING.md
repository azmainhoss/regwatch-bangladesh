# Deep research prompt: collecting circulars (paste everything below the line into a chat with deep research on)

---

I'm building a regulatory-monitoring SaaS in Bangladesh. Its first job is to collect every new circular, circular letter, guideline and notice that Bangladesh Bank publishes on bb.org.bd, as fast and as reliably as possible. Each item comes as a PDF in English, Bangla or both. Later we'll add NBR, BSEC, IDRA and FRC, so the approach must scale to many regulator websites, each built differently.

What I already know from my own testing:
- The circular list page (https://www.bb.org.bd/en/index.php/mediaroom/circular) returns all ~4,800 circulars in one 2.6 MB HTML page.
- A date-range search form on the same page returns only recent items (~50 KB).
- PDFs download directly and send ETag and Last-Modified headers.
- There's no RSS, sitemap, API or email alert.
- The site sits behind an F5/TSPD bot check. At times our earlier crawler got challenge pages ("What code is in the image?") after roughly 20 downloads. Other times, 100+ downloads went through with no problem.
- Volume is about 300 new circulars a year, plus a one-time backlog of ~4,800.

I want a wide, current (2025-2026) survey of how people collect web data at this level, not just "write a small script". Please cover:

1. **Managed scraping and crawling APIs.**
   - Services: Firecrawl, Apify, Zyte API, ScrapingBee, ScraperAPI, ZenRows, Bright Data (Web Unlocker, Scraping Browser), Oxylabs, Browserbase, Browserless, Steel, Hyperbrowser, Diffbot, Jina Reader, Exa, Tavily extract, Spider.cloud, and anything newer.
   - For each: what it does, pricing at my volume, JavaScript rendering, PDF handling, change-detection or monitoring features, webhooks, reliability record, data residency, and whether it can be pointed at one site on a schedule.

2. **Website change-detection and monitoring services**, hosted and self-hosted.
   - Hosted: Visualping, Distill.io, Browse AI, Kadoa, Thunderbit, Hexomatic, Fluxguard, PageCrawl.
   - Self-hosted: changedetection.io.
   - Do any watch a page and fire a webhook with structured new rows?

3. **AI or agentic extraction tools** that turn pages into structured data, or adapt when a site's layout changes: Crawl4AI, ScrapeGraphAI, Firecrawl extract, Kadoa, Browser Use, Stagehand, Skyvern, Playwright MCP, AgentQL.
   - Are they worth it for regulator sites that change rarely but must never be missed?
   - How do they handle 5+ different regulator websites?

4. **Self-hosted scraping platforms** I could run on my own Bangladeshi server and call from my main app with my own API key: Crawlee, Scrapy + Scrapyd, Scrapling, Katana, spider-rs, Playwright/Puppeteer clusters, Firecrawl self-hosted, Crawl4AI server, browserless self-hosted.
   - For each: RAM/CPU needs, queueing and retries, scheduling, monitoring dashboards, how easily a new site can be added.

5. **Bot checks such as F5/TSPD.**
   - What do these services and tools do when they meet one?
   - Which ones advertise "unblocking", and how do they do it?
   - Is it legal and within the terms of service for a Bangladeshi business to use those features against a government website?
   - What are the realistic legitimate options: allow-listing by the bank, an official data-sharing agreement, polite pacing, and making requests through a real browser session?

6. **Reliability design for "never miss a circular".**
   - Detecting a challenge page versus a real empty result.
   - Watching several signals at once (list page, homepage ticker, date search, news sites, Bangladesh Bank's Facebook page).
   - Backfilling ~4,800 PDFs safely.
   - Alerting a human when collection breaks.
   - How do established regulatory-intelligence companies (RegAlert/regalert.today, CUBE, Regology, Corlytics, Compliance.ai) collect from thousands of regulator sites?

7. **A clear recommendation.** Compare three options:
   - (a) a managed API or service;
   - (b) a self-hosted scraping service with its own API that my app calls;
   - (c) a small purpose-built collector.

   For each give the monthly cost, speed (minutes from publication to detection), reliability, maintenance effort, how it scales to 5+ regulators, and vendor lock-in. Then say which one you would pick for my case, and why.

Cite sources for every price and claim, and mark anything you could not verify.
