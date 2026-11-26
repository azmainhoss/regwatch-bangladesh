# Amar Circular: what changed

A plain record of the changes, newest first, so anyone can see what the app went through and why. Technical detail
is in the commits (`git log`) and the linked documents.

---

## 26 November 2026: FEPD-2 Circular Letter No. 03 analysed

- New circular (price verification platform and a central price monitoring cell for Authorized Dealers, due
  1 January 2027) analysed and uploaded; all 15 points passed the checks and it shows as Ready.
- Public circular pages now print "Who it applies to" as readable names (Authorised dealers) instead of
  codes like AUTHORIZED_DEALER.

## 26 November 2026: search engine pages (SEO)

- **Keyword research** (`docs/seo/KEYWORDS.md`): "bangladesh bank circular" is searched about 12,100 times a
  month in Bangladesh, "brpd circular" 1,900, "bfiu circular 26" 1,000, all with low difficulty. People search by
  department and number, which is how circular pages are already addressed.
- **List pages** that search engines can read: `/circulars` (newest), `/circulars/<department>` (BRPD, FEPD, DOS,
  BFIU and 22 more), `/circulars/<year>` and `/circulars/topic/<subject>` (29 subjects). A page exists only when at
  least 3 of its circulars have a summary. Each has a short unique intro, Bangla line, breadcrumbs and links to all
  the other lists.
- **Circular pages:** title starts with the full reference and year ("BRPD Circular No. 16/2022: ..."), a Bangla
  reference line ("বিআরপিডি সার্কুলার নং ১৬/২০২২"), a link to the original PDF on bb.org.bd, subject links and up
  to 8 related circulars.
- **Site-wide:** keyword title and description, Organization and WebSite (with search box) structured data, footer
  links to the main lists, Search Console and Bing verification tags read from `NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION`
  and `NEXT_PUBLIC_BING_SITE_VERIFICATION`, `/llms.txt` for AI search, and the sitemap now lists the list pages too.
- **IndexNow:** the live server tells Bing about new pages every hour (`modules/library/indexnow.py`, key file in
  `frontend/public/`). Google reads the sitemap instead.
- Future SEO work is dated in TickTick, project "amarcircular seo".

---

## 24 November 2026 (night): site behind Cloudflare

- **The domain's DNS moved from Spaceship to Cloudflare** (free plan). The domain stays registered at Spaceship.
  Visitors now reach the site through Cloudflare, which hides the server's address and adds DDoS protection and
  caching. Encryption is "Full (strict)": Cloudflare checks the server's own certificate.
- **The server trusts Cloudflare's addresses**, so the sign-up and sign-in limits still count each visitor on their
  own instead of treating everyone as one Cloudflare address.

---

## 26 November 2026: email is on

- Brevo SMTP key installed on the server. A test daily email was delivered to the owner (Brevo log: Delivered).
- "Forgot password?" is back under the sign-in password.
- The daily email of new circulars goes to every registered person at 19:30 Dhaka time, covering circulars added
  after email was switched on (26 Nov, 06:52 UTC).

---

## 25 November 2026 (night): no human review anywhere; one meaning of "AI verified"

- **"AI verified" now means one thing everywhere** (list, reader, search, circular pages): at least one point of
  the circular passed the automated checks against the page. Until then it is an **AI draft**. Before, 282
  circulars showed "AI verified" in the list while the reader said "AI draft".
- **No link or point waits for a person** (owner's rule). A link the machine confirms keeps its type (amends,
  repeals, ...); one it cannot confirm is kept as a plain "cites" link that never changes a circular's in-force
  status; a link that fails its checks is dropped from History & links. 174 requirement points that were parked
  for a person were sent back through the automated checks.
- The admin-only tag now says "N links being checked" (the automated checks are still running), not
  "awaiting review".
- **Daily email (on hold with email):** sent every day at 19:30 Dhaka time to every registered person who has not
  unsubscribed, with how many circulars came that day and each one listed (also on days with none). No AI labels
  in emails, and no welcome email.
- **Known limit:** the second reading of page images uses Gemini's free quota. All 7 keys reached today's limit;
  5,879 sentences on 759 pages wait, and the free quota clears roughly 230–500 a day.

---

## 25 November 2026 (evening): sign-up in 3 steps, emails ready

- **Sign-up is now 3 steps** for everyone: email and password (the account is made here), then name and phone,
  then company and designation, with "Step N of 3". Owner-approved.
- **Forgot password:** "Forgot password?" under the sign-in password opens `/reset-password`. The emailed link
  works for one hour and only once.
- **Emails (owner-approved designs):** welcome email after sign-up; the branded daily digest of new circulars (each
  with its AI verified / AI draft mark and first summary point, linking to the circular's page); password reset.
  Digest and welcome come from "Amar Circular" <insights@amarcircular.com>, alerts and resets from
  "Amar Circular Alerts" <alerts@amarcircular.com>.
- **One-click unsubscribe** from the daily digest: mail apps' "Unsubscribe" button works without signing in, and
  the footer link opens a one-button page. It turns off only the digest.
- **Email is on hold (owner, 25 Nov):** Brevo's phone verification did not arrive, so no SMTP key is on the server
  and nothing is sent. While it is off, "Forgot password?" is hidden and the reset page asks people to write to
  insights@amarcircular.com. To switch email on later: `ssh -t amarcircular 'sudo bash /opt/regwatch/app/deploy/set-smtp.sh'`.

---

## 25 November 2026 (later): dashboard, search and reader improvements

- **Dashboard filters:** the five largest departments are pills, with **More departments** (searchable, full names
  where known, counts) and a searchable **Category** list. On phones both open as a sheet from the bottom.
  Department and category now apply together.
- **Filters are in the address** (`?dept=BRPD&topic=…&q=…&box=week`), so a filtered view can be shared, and Back
  and refresh keep it. Coming back to the dashboard returns to the same scroll position.
- **"Showing 30 of 4,786"** above the list; "Load 30 more" below it.
- **Reader actions in a clearer order:** Source pages, Mind map, History & links, Assign to team, then Save and
  Email. Original PDF, compare and add-to-register are under **More** (the PDF stays up front when a circular has
  no readable pages). On phones: Source pages, Mind map and Save, with the rest under More.
- **Search:** "Published" presets (last 30 days, last 12 months, last 3 years, this year) replace the two
  free-text year boxes, and **Sort by: Newest first / Best match**. Newest first stays the default.
- **Keyboard:** besides J/K (next/previous), **P** opens the source pages and **S** saves to Read later.
- **Mind map:** zoom in and out (up to 250%) and drag or scroll to move around large maps.
- **Navigation:** Dashboard stays highlighted on circular and History & links pages.
- **3-step sign-up** is built and can be tried at `amarcircular.com/?signup=steps`; everyone else keeps the
  one-form sign-up until it is approved.
- **Email drafts** (daily digest, welcome, password reset, saved-circular alert) are written for approval; nothing
  is sent.

---

## 25 November 2026: circulars Google can read

- **Every circular now has its own address**, for example
  `/circular/brpd/49-2024-transfer-of-jute-sector-outstanding-loans-to-block`. The page is built on the server, so
  Google and shared links see the real summary, what changed, the requirements and the dates, each with the page it
  comes from. "Open with source pages" opens the full reader.
- **Only circulars with an AI verified analysis are indexed** (659 at launch). The others still open but tell
  search engines not to index them, so thousands of empty pages do not hurt the site.
- **sitemap.xml and robots.txt** now exist. The library app (/dashboard) is not indexed; the circular pages are.
- The whole site now renders on the server first, instead of a loading spinner until JavaScript runs.

---

## 24 November 2026 (late): access rule, trust words, cited names

- **Visitor access:** a device's first 7 days are completely open, with no counter and no register prompts. From
  day 8, 5 more circulars can be read in full, then a free registration is asked. (Before: 3 free circulars.)
  Read later, lists and assigning always need an account.
- **Trust words:** readers now see only **AI verified** (points passed the automated checks against the page) or
  **AI draft**. No tooltips. Points not yet confirmed show "Page N · AI draft". Circulars with no analysis at all
  get no trust badge.
- **Cites:** the circulars a circular cites now show by name or number (for example "Guidelines for Foreign
  Exchange Transactions 2018…"). Before, unconfirmed links showed only "References a circular".

---

## 24 November 2026 (night): first audit fixes

- **Reader: "Back links" is now "Cites"**, and a new **"Cited by"** row lists newer circulars that cite this one
  without changing it (references, implements). Amended / Replaced / Repealed by stay as before.
- **Ask prompts for visitors** now say **Register free** (main button) with **Sign in** beside it. Before, the
  circular's Ask box said "Register free to ask" but its button said "Sign in".
- **Branded "page not found"** with a search box and the five newest circulars.
- **"Install the app"** is offered only from the third visit, or right after someone saves a circular, never on a
  first look.
- **Email:** Brevo authenticates amarcircular.com (DKIM, DMARC). Mail sent to insights@amarcircular.com is
  forwarded to the owner. No email is sent by the app yet (SMTP is still off).
- The full audit checklist is in `docs/audit-2026-11-24-plan.md`.

---

## 24 November 2026 (evening): home page

- **New home page at amarcircular.com.** A headline ("Grab the updates first!"), one line on what the site
  does, and right under it the **Today / This week / This month / Read later** cards. A card opens the dashboard
  with that filter on. The picture beside it is a real point from BRPD-1 Circular Letter No. 40, linked to its
  highlighted sentence on page 1; clicking it opens that circular. **Ask a question** sits below and answers right
  there. (The first version also had an "Open the library" button and three numbers; the owner asked for the cards
  in their place.)
- **Notice at the bottom of every page:** "This is not an official reference. Please verify the original reference
  at your own responsibility before making any decision."
- **The dashboard moved to /dashboard** and works as before. Old links such as `/?doc=…` (emails, alerts, bookmarks)
  still open the right circular there.
- **Card look** on both pages: each card has its own light tint (Today light red, This week light blue, This
  month light amber, Read later light grey). The card whose filter is on turns solid green with a "✓ Selected" tag,
  so it is clear what the list is showing. Today shows a red NEW tag and a red number when something was issued
  today. (The first version used strong, different colours per card; readers could not tell which one was selected.)

---

## 24 November 2026: go-live day

### Hosting and setup
- **Live at https://amarcircular.com.** One Spaceship VPS in Singapore (Standard 1: 1 core, 2 GB RAM, 25 GB
  disk), on the yearly plan ($42.44/year after the 7-day free trial). It runs the backend (FastAPI), the website
  (Next.js), the SQLite database and every PDF. Caddy gives HTTPS automatically.
- **Domain and DNS** are on Spaceship: `amarcircular.com` points to `104.207.77.129`, and `www` redirects to it.
- **Server security:** SSH only with a key, on port 22022 (Spaceship's port), with password login off. Firewall
  allows SSH, 80 and 443 only. fail2ban, automatic security updates and a 2 GB swap file are on.
- **Data moved from the laptop:** the database (4,791 circulars) and 1.7 GB of PDFs, integrity checked.
- **Demo logins:** all 22 demo and test logins (passwords were in the code) are switched off.
- **Backups:** a nightly copy at 02:30 Dhaka time to Cloudflare R2 (bucket `amarcircular-backup`), encrypted
  before upload. A restore was tested. The encryption passwords are with the owner.
- **Gemini:** Google refuses Gemini calls from the server's location, so they go through a small Cloudflare Worker
  relay that only the server may use. Page reading and "Ask a question" work through it.
- **The hourly bb.org.bd check runs on the server** (9:00 to 19:00 Dhaka). On its first day it found 4 new
  circulars by itself.

### Name and access
- **RegWatch is now Amar Circular** everywhere a user looks: name, logo, app icons, emails. Internal names in the
  code and server stay as they were.
- **Sign-up and sign-in:** visitors can read the dashboard and **3 circulars free**. After that, any click asks
  them to register. Register asks for name, email, phone, company, designation and password; next time they sign
  in with email and password. Readers stay signed in for 30 days.
- **Admin:** sign in at `/admin/login`. The admin console has a **Sign-ups** tab (everyone who registered, with
  search and a CSV download).

### What readers see on a circular
- **No hidden points.** Before, about 40% of summary points were hidden behind "N points are not shown here".
  Now every point is shown. Points confirmed against the page say "Page N · Checked"; the rest say **"Check page N"**,
  which opens the highlighted lines.
- **Fewer false failures** in the second page reading (Gemini reads the page image again and must agree with our
  text):
  - the strip read around a sentence is now wide enough (it often missed the sentence);
  - when it does miss, the whole page is read instead;
  - Bangla spelling variants (hasant, ি/ী, ু/ূ, । and .) no longer count as differences.
  Numbers, "not" words and circular numbers are still compared exactly.
- **Automatic number correction.** When both independent readings agree on a number and ours differs (for example
  ১৭৭ against ৭১৭), ours is corrected automatically, in the point and in its quote. The same number in the same
  place elsewhere in that circular is corrected too. 31 sentences were corrected on day one. Nothing here needs a
  person.
- Full review of the 10 cases behind these changes: `docs/review-2026-11-24-hidden-points.md`.

### Dashboard
- **Today / This week / This month / Read later cards:** clicking one jumps to the list and shows a chip such as
  "Since Sunday ✕" with the count. Click ✕ or the card again to show all.
- **Circular numbers for new departments:** new circulars from departments the checker did not know (BRD, FDIPP, …)
  now get their number, e.g. "BRD Circular No. 04".

### History & links (now automatic)
- **How it works:** when a circular is analysed, every other circular it mentions becomes a link (amends,
  repeals, supersedes, replaces, clarifies, implements or references). The app finds that circular in the library.
  It shows the links under "History & links" and marks older circulars as "Amended", "Replaced" or "Repealed".
- **Before:** every amends/repeals/supersedes link waited for a person, so no circular was ever marked as
  changed. Many cited circulars were not found because citations write the number differently.
- **Now, matching:** a citation that leaves out the department's section number ("ACD Circular No. 03" for
  "ACD-1 Circular No. 03/2026") or uses the old department name ("FE" for "FEPD") is matched when the date it gives
  agrees. The date also picks between two candidates. Never a guess.
- **Now, confirmation:** a change link is confirmed by the machine when the quote uses change words (also
  "replaced by", "extended", "relaxed", প্রতিস্থাপিত, বর্ধিত, শিথিল) and names the circular, exactly one older
  library circular matches, and the cited date agrees. The older circular's status changes by itself.
- **Live result:** 172 more citations matched; 68 change links confirmed (from 0); 63 circulars now show
  "Amended by" / "Replaced by" / "Repealed by" with a link to the newer circular; 172 circulars show links
  (from 66). Example: BRPD Circular No. 14/2012 shows "Amended by BRPD Circular No. 15/2024".
- **Still mentions only:** links whose quote is not yet confirmed by the page reading, whose quote has no
  change words, or whose cited circular is not in the library (very old circulars, GFET guidelines). They become
  confirmed by themselves when the page reading or the library catches up.

### Fixes along the way
- "Ask a question" no longer gives a server error when the answer service is unavailable; it lists the matching
  pages instead.
- A circular opened by a visitor no longer shows a red "sign in" error.

### Decisions
- **Summaries for new circulars (Phase 1):** run by hand on the laptop. Anthropic's consumer terms do not allow a
  scheduled, unattended Pro login for a commercial service. Phase 2 (Claude Sonnet through the API, about $10 a
  month) starts with the first paying bank.
- **Minimal human involvement:** no step should wait for a person by default.

### Known open items
- About 270 sentences where the two page readings disagree with each other stay "Check page N".
- Add a card to Spaceship before the trial ends, or the server stops.
